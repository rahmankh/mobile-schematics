"""
Payment intents that sit between checkout and entitlement.

A row stays PENDING until the gateway verify() succeeds. Only then may
SchematicPurchase or UserSubscription be inserted.
"""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class PaymentTransaction(models.Model):
    """
    One gateway session (Zarinpal Authority / IDPay ID).

    `authority` is the unguessable handle the gateway echoes on callback, so
    verify can run without a logged-in session (browser redirect).
    """

    class Purpose(models.TextChoices):
        SCHEMATIC = 'schematic', _('خرید تکی شماتیک')
        WALLET = 'wallet', _('شارژ کیف پول')
        SUBSCRIPTION = 'subscription', _('خرید اشتراک')  # legacy rows only; new checkouts are rejected.

    class Status(models.TextChoices):
        PENDING = 'pending', _('در انتظار پرداخت')
        PAID = 'paid', _('پرداخت‌شده')
        FAILED = 'failed', _('ناموفق')
        CANCELED = 'canceled', _('لغو شده')

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='payment_transactions',
        verbose_name=_('کاربر'),
    )
    purpose = models.CharField(_('نوع خرید'), max_length=20, choices=Purpose.choices)
    amount = models.DecimalField(_('مبلغ (تومان)'), max_digits=10, decimal_places=0)
    authority = models.CharField(_('کد Authority'), max_length=64, unique=True, db_index=True)
    gateway = models.CharField(_('درگاه'), max_length=32, default='mock')
    status = models.CharField(
        _('وضعیت'),
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    schematic = models.ForeignKey(
        'schematics.Schematic',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payment_transactions',
        verbose_name=_('شماتیک'),
    )
    plan = models.ForeignKey(
        'subscriptions.Plan',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='payment_transactions',
        verbose_name=_('پلن اشتراک'),
    )
    ref_id = models.CharField(_('کد پیگیری درگاه'), max_length=64, blank=True)
    description = models.CharField(_('توضیح'), max_length=255, blank=True)
    verified_at = models.DateTimeField(_('زمان تایید'), null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    # HMAC of the one-time guest claim token. Empty for authenticated checkouts.
    claim_token_hash = models.CharField(max_length=64, blank=True, default='')
    # True only when this checkout created the user row. Existing guests must not
    # receive a session from a later payment on their phone number.
    guest_account_created = models.BooleanField(default=False)
    claimed_at = models.DateTimeField(_('زمان صدور نشست مهمان'), null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = _('تراکنش پرداخت')
        verbose_name_plural = _('تراکنش‌های پرداخت')
        indexes = [
            models.Index(fields=['user', 'status'], name='idx_pay_user_status'),
        ]

    def __str__(self) -> str:
        return f'{self.authority} ({self.get_status_display()})'
