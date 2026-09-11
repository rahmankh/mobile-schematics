"""
Checkout orchestration.

create_payment_request() persists a PENDING transaction after the gateway
issues an authority. fulfill_paid_transaction() is the only function allowed
to insert SchematicPurchase / UserSubscription, and only when status flips
pending → paid after a successful verify().
"""

from __future__ import annotations

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.reverse import reverse

from accounts.services import get_or_create_checkout_user, issue_jwt_for
from schematics.models import Schematic
from schematics.services import AlreadyPurchased, SchematicNotPurchasable, assert_schematic_purchasable, fulfill_schematic_purchase
from subscriptions.models import Plan
from subscriptions.services import fulfill_subscription

from .gateways import get_gateway
from .models import PaymentTransaction


class PaymentError(Exception):
    """Base checkout error (mapped to 400 by the view)."""


class PaymentConflict(PaymentError):
    """Mapped to HTTP 409 (already owned, etc.)."""


def create_payment_request(*, user, purpose: str, schematic_id=None, plan_id=None, request=None) -> tuple[PaymentTransaction, str]:
    """
    Validate the cart, ask the gateway for an authority, then store PENDING.

    No SchematicPurchase or UserSubscription is written here.
    """
    if purpose == PaymentTransaction.Purpose.SCHEMATIC:
        if not schematic_id:
            raise PaymentError('schematic_id الزامی است.')
        try:
            schematic = Schematic.objects.get(pk=schematic_id)
        except Schematic.DoesNotExist as exc:
            raise PaymentError('شماتیک مورد نظر یافت نشد.') from exc
        try:
            assert_schematic_purchasable(user, schematic)
        except AlreadyPurchased as exc:
            raise PaymentConflict(str(exc)) from exc
        except SchematicNotPurchasable as exc:
            raise PaymentError(str(exc)) from exc
        amount = schematic.price
        plan = None
        description = f'Schematic #{schematic.pk} {schematic.title}'[:255]
    elif purpose == PaymentTransaction.Purpose.SUBSCRIPTION:
        if not plan_id:
            raise PaymentError('plan_id الزامی است.')
        try:
            plan = Plan.objects.get(pk=plan_id, is_active=True)
        except Plan.DoesNotExist as exc:
            raise PaymentError('پلن انتخابی معتبر یا فعال نیست.') from exc
        schematic = None
        amount = plan.price
        description = f'Subscription plan #{plan.pk} {plan.title}'[:255]
    else:
        raise PaymentError('purpose نامعتبر است.')

    if amount <= 0:
        raise PaymentError('مبلغ پرداخت باید بزرگ‌تر از صفر باشد.')

    callback_url = getattr(settings, 'PAYMENT_CALLBACK_URL', '') or _default_callback(request)
    gateway = get_gateway()
    issued = gateway.request_payment(
        amount=int(amount),
        description=description,
        callback_url=callback_url,
        extra={'purpose': purpose, 'user_id': user.id},
    )

    return PaymentTransaction.objects.create(
        user=user,
        purpose=purpose,
        amount=amount,
        authority=issued.authority,
        gateway=gateway.name,
        status=PaymentTransaction.Status.PENDING,
        schematic=schematic,
        plan=plan,
        description=description,
    ), issued.payment_url


def start_guest_schematic_checkout(
    *,
    phone_number: str,
    schematic_id,
    request=None,
) -> tuple[PaymentTransaction, str, str]:
    """
    Guest single-copy checkout: phone + schematic, no password.

    The schematic is validated *before* creating a user so a typo or a free
    document cannot spawn an empty guest account. Returns
    (txn, payment_url, account_status) where account_status is one of
    created / existing_guest / existing_registered.
    """
    try:
        schematic = Schematic.objects.get(pk=schematic_id)
    except Schematic.DoesNotExist as exc:
        raise PaymentError('شماتیک مورد نظر یافت نشد.') from exc
    if schematic.is_free or schematic.price <= 0:
        raise PaymentError('این شماتیک برای خرید تکی در دسترس نیست.')

    user, created = get_or_create_checkout_user(phone_number)
    if created:
        account_status = 'created'
    elif user.is_guest:
        account_status = 'existing_guest'
    else:
        account_status = 'existing_registered'

    txn, payment_url = create_payment_request(
        user=user,
        purpose=PaymentTransaction.Purpose.SCHEMATIC,
        schematic_id=schematic.pk,
        request=request,
    )
    return txn, payment_url, account_status


def verify_access_payload(user) -> dict:
    """
    Extra keys for GET /payments/verify/.

    Guests (no login password) receive JWT so they can download immediately.
    Registered technicians must sign in — issuing JWT here would let anyone who
    knows a phone number hijack that account by paying for a cheap schematic.
    """
    payload = {
        'is_guest': user.is_guest,
        'login_required': not user.is_guest,
        'phone_number': user.phone_number,
    }
    if user.is_guest:
        payload.update(issue_jwt_for(user))
    return payload


def _default_callback(request) -> str:
    if request is None:
        return '/api/v1/payments/verify/'
    return request.build_absolute_uri(reverse('payments:payment-verify'))


def mark_canceled(txn: PaymentTransaction) -> None:
    """User aborted on the gateway page (Status=NOK). Never fulfill."""
    if txn.status == PaymentTransaction.Status.PENDING:
        txn.status = PaymentTransaction.Status.CANCELED
        txn.save(update_fields=['status'])


def mark_failed(txn: PaymentTransaction, message: str = '') -> None:
    """Gateway verify declined. Never fulfill."""
    if txn.status == PaymentTransaction.Status.PENDING:
        txn.status = PaymentTransaction.Status.FAILED
        if message:
            txn.description = f'{txn.description} | {message}'[:255]
        txn.save(update_fields=['status', 'description'])


def verify_and_fulfill(*, authority: str, gateway_ok: bool) -> PaymentTransaction:
    """
    Confirm the authority with the gateway, then grant entitlements.

    Idempotent: a second call on an already-PAID row returns it unchanged.
    """
    try:
        txn = PaymentTransaction.objects.select_related('user', 'schematic', 'plan').get(
            authority=authority
        )
    except PaymentTransaction.DoesNotExist as exc:
        raise PaymentError('تراکنش پرداخت یافت نشد.') from exc

    if txn.status == PaymentTransaction.Status.PAID:
        return txn

    if txn.status != PaymentTransaction.Status.PENDING:
        raise PaymentError('این تراکنش قابل تایید نیست.')

    if not gateway_ok:
        mark_canceled(txn)
        raise PaymentError('پرداخت توسط کاربر لغو شد.')

    result = get_gateway().verify_payment(authority=txn.authority, amount=int(txn.amount))
    if not result.success:
        mark_failed(txn, result.message)
        raise PaymentError(result.message or 'درگاه پرداخت، تراکنش را تایید نکرد.')

    with transaction.atomic():
        # Lock the row so two parallel callbacks cannot double-fulfill.
        txn = PaymentTransaction.objects.select_for_update().get(pk=txn.pk)
        if txn.status == PaymentTransaction.Status.PAID:
            return txn
        txn.status = PaymentTransaction.Status.PAID
        txn.ref_id = result.ref_id
        txn.verified_at = timezone.now()
        txn.save(update_fields=['status', 'ref_id', 'verified_at'])
        _grant_entitlement(txn)

    return PaymentTransaction.objects.select_related('user', 'schematic', 'plan').get(pk=txn.pk)


def _grant_entitlement(txn: PaymentTransaction) -> None:
    """Insert commerce rows. Called only from verify_and_fulfill inside an atomic block."""
    if txn.purpose == PaymentTransaction.Purpose.SCHEMATIC and txn.schematic_id:
        fulfill_schematic_purchase(txn.user, txn.schematic, price_paid=txn.amount)
    elif txn.purpose == PaymentTransaction.Purpose.SUBSCRIPTION and txn.plan_id:
        fulfill_subscription(txn.user, txn.plan)
    else:
        raise PaymentError('تراکنش هدف مشخصی برای فعال‌سازی ندارد.')
