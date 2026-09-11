"""
Subscription plans and per-user entitlement records.

`UserSubscriptionQuerySet.active_subscriptions` is the single indexed query used by
HasActiveSubscription and Schematic.user_can_download. Keep the (user, status, end_date)
index in sync with that filter.
"""

from datetime import timedelta

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class Plan(models.Model):
    """Sellable subscription SKU (monthly / quarterly / yearly)."""

    title = models.CharField(_('عنوان پلن'), max_length=100, unique=True)
    description = models.TextField(_('توضیحات'), blank=True)
    price = models.DecimalField(
        _('قیمت (تومان)'),
        max_digits=10,
        decimal_places=0,
        validators=[MinValueValidator(0)],
    )
    duration_days = models.PositiveIntegerField(_('مدت اعتبار (روز)'), default=30)
    is_active = models.BooleanField(_('فعال'), default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('پلن اشتراک')
        verbose_name_plural = _('پلن‌های اشتراک')
        ordering = ['price']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(price__gte=0),
                name='plan_price_non_negative',
            ),
        ]

    def __str__(self):
        return f'{self.title} ({self.duration_days} روز) - {self.price:,} تومان'


class UserSubscriptionQuerySet(models.QuerySet):
    """QuerySet helpers that encode the 'currently valid' definition in one place."""

    def active_subscriptions(self):
        """Rows that are both flagged ACTIVE and still inside their validity window."""
        now = timezone.now()
        return self.filter(
            status=UserSubscription.StatusChoices.ACTIVE,
            end_date__gt=now,
        )


class UserSubscriptionManager(models.Manager):
    """Default manager exposing `has_active_subscription(user)` for permission checks."""

    def get_queryset(self):
        return UserSubscriptionQuerySet(self.model, using=self._db)

    def has_active_subscription(self, user) -> bool:
        """
        Fast existence check used on every paid download.

        Relies on Index(user, status, end_date). Anonymous / missing users are False
        without hitting the database.
        """
        if not user or not getattr(user, 'is_authenticated', False):
            return False
        return self.get_queryset().active_subscriptions().filter(user=user).exists()


class UserSubscription(models.Model):
    """
    One subscription period for a technician.

    Multiple ACTIVE rows can exist (renewals stack: purchase view starts the next
    period at the current end_date). Validity is `status=active AND end_date > now`.
    """

    class StatusChoices(models.TextChoices):
        ACTIVE = 'active', _('فعال')
        EXPIRED = 'expired', _('منقضی‌شده')
        CANCELED = 'canceled', _('لغو شده')

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='subscriptions',
        verbose_name=_('کاربر'),
    )
    plan = models.ForeignKey(
        Plan,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='user_subscriptions',
        verbose_name=_('پلن'),
    )
    start_date = models.DateTimeField(_('تاریخ شروع'), default=timezone.now)
    end_date = models.DateTimeField(_('تاریخ پایان'))
    status = models.CharField(
        _('وضعیت'),
        max_length=20,
        choices=StatusChoices.choices,
        default=StatusChoices.ACTIVE,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = UserSubscriptionManager()

    class Meta:
        verbose_name = _('اشتراک کاربر')
        verbose_name_plural = _('اشتراک‌های کاربران')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'status', 'end_date'], name='idx_sub_user_status_end'),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_date__gt=models.F('start_date')),
                name='subscription_end_after_start',
            ),
        ]

    def __str__(self):
        plan_title = self.plan.title if self.plan else 'نامشخص'
        return f'{self.user} - {plan_title} ({self.get_status_display()})'

    @property
    def is_valid(self) -> bool:
        """True when this row would pass the permission check right now."""
        return self.status == self.StatusChoices.ACTIVE and self.end_date > timezone.now()

    def save(self, *args, **kwargs):
        # Derive end_date from the plan when the caller only supplied a start.
        if not self.end_date and self.plan:
            start = self.start_date or timezone.now()
            self.end_date = start + timedelta(days=self.plan.duration_days)
        super().save(*args, **kwargs)
