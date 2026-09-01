

from django.db import models
from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from datetime import timedelta


class Plan(models.Model):
    title = models.CharField(_("Plan Title"), max_length=100)
    description = models.TextField(_("Description"), blank=True)
    price = models.DecimalField(_("Price (Toman/Rial)"), max_digits=10, decimal_places=0)
    duration_days = models.PositiveIntegerField(_("Duration (Days)"), default=30)
    is_active = models.BooleanField(_("Is Active"), default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Plan")
        verbose_name_plural = _("Plans")
        ordering = ['price']

    def __str__(self):
        return f"{self.title} ({self.duration_days} days) - {self.price:,}"


class UserSubscription(models.Model):
    STATUS_CHOICES = (
        ('active', _('Active')),
        ('expired', _('Expired')),
        ('canceled', _('Canceled')),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='subscriptions',
        verbose_name=_("User")
    )
    plan = models.ForeignKey(
        Plan,
        on_delete=models.SET_NULL,
        null=True,
        related_name='user_subscriptions',
        verbose_name=_("Plan")
    )
    start_date = models.DateTimeField(_("Start Date"), default=timezone.now)
    end_date = models.DateTimeField(_("End Date"))
    status = models.CharField(_("Status"), max_length=20, choices=STATUS_CHOICES, default='active')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("User Subscription")
        verbose_name_plural = _("User Subscriptions")
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user} - {self.plan.title if self.plan else 'Unknown'} ({self.status})"

    @property
    def is_valid(self):
        """بررسی اعتبار زمانی و وضعیت اشتراک"""
        return self.status == 'active' and self.end_date > timezone.now()

    def save(self, *args, **kwargs):
        if not self.end_date and self.plan:
            self.end_date = (self.start_date or timezone.now()) + timedelta(days=self.plan.duration_days)
        super().save(*args, **kwargs)