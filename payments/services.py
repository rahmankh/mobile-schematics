"""
Checkout orchestration.

create_payment_request() persists a PENDING transaction after the gateway
issues an authority. fulfill_paid_transaction() is the only function allowed
to insert SchematicPurchase / UserSubscription, and only when status flips
pending → paid after a successful verify().
"""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from accounts.services import get_or_create_checkout_user, issue_jwt_for, public_account_payload
from schematics.models import Schematic
from schematics.services import AlreadyPurchased, SchematicNotPurchasable, assert_schematic_purchasable, fulfill_schematic_purchase

from .claims import claim_token_matches, generate_claim_token, hash_claim_token
from .gateways import HTML_CALLBACK_PATH, get_gateway
from .models import PaymentTransaction

SUBSCRIPTION_RETIRED_MESSAGE = (
    'خرید اشتراک دیگر پشتیبانی نمی‌شود. از شارژ کیف پول یا خرید تکی استفاده کنید.'
)
MIN_WALLET_TOPUP = 10000


class PaymentError(Exception):
    """Base checkout error (mapped to 400 by the view)."""


class PaymentConflict(PaymentError):
    """Mapped to HTTP 409 (already owned, etc.)."""


class PaymentClaimDenied(PaymentError):
    """Mapped to HTTP 403 (wrong/unusable guest claim)."""


def _unique_schematic_ids(*groups) -> list[int]:
    """Flatten schematic id arguments, drop junk, and keep first-seen order."""
    ids: list[int] = []
    seen: set[int] = set()
    for group in groups:
        if group is None:
            continue
        if isinstance(group, (str, bytes)):
            group = [group]
        elif isinstance(group, int):
            group = [group]
        else:
            try:
                group = list(group)
            except TypeError:
                group = [group]
        for raw in group:
            try:
                pk = int(raw)
            except (TypeError, ValueError):
                continue
            if pk not in seen:
                seen.add(pk)
                ids.append(pk)
    return ids


def resolve_payable_schematics(user, *, schematic_id=None, schematic_ids=None) -> list[Schematic]:
    """
    Build the charged schematic list for a checkout.

    Duplicates, missing rows, free/unpriced documents, and already-owned
    copies are skipped. An empty result raises PaymentError / PaymentConflict
    with the same messages single-item checkout used.
    """
    ids = _unique_schematic_ids(schematic_ids, schematic_id)
    if not ids:
        raise PaymentError('schematic_id الزامی است.')

    found = {item.pk: item for item in Schematic.objects.filter(pk__in=ids)}
    payable: list[Schematic] = []
    already_owned = 0
    unpayable = 0
    for pk in ids:
        schematic = found.get(pk)
        if schematic is None:
            unpayable += 1
            continue
        try:
            assert_schematic_purchasable(user, schematic)
        except AlreadyPurchased:
            already_owned += 1
            continue
        except SchematicNotPurchasable:
            unpayable += 1
            continue
        payable.append(schematic)

    if payable:
        return payable
    if not found:
        raise PaymentError('شماتیک مورد نظر یافت نشد.')
    if already_owned and unpayable == 0:
        raise PaymentConflict('این شماتیک را قبلاً خریداری کرده‌اید.')
    raise PaymentError('این شماتیک برای خرید تکی در دسترس نیست.')


def create_payment_request(
    *,
    user,
    purpose: str,
    schematic_id=None,
    schematic_ids=None,
    plan_id=None,
    amount=None,
    request=None,
    claim_token_hash: str = '',
    guest_account_created: bool = False,
) -> tuple[PaymentTransaction, str]:
    """
    Validate the cart, ask the gateway for an authority, then store PENDING.

    No SchematicPurchase is written here. Subscription checkouts are retired.
    """
    if purpose == PaymentTransaction.Purpose.SUBSCRIPTION:
        raise PaymentError(SUBSCRIPTION_RETIRED_MESSAGE)

    batch_ids: list[int] = []
    if purpose == PaymentTransaction.Purpose.SCHEMATIC:
        payable = resolve_payable_schematics(
            user,
            schematic_id=schematic_id,
            schematic_ids=schematic_ids,
        )
        schematic = payable[0]
        batch_ids = [item.pk for item in payable]
        amount = sum((item.price for item in payable), Decimal('0'))
        plan = None
        if len(payable) == 1:
            description = f'Schematic #{schematic.pk} {schematic.title}'[:255]
        else:
            description = f'Batch schematics {", ".join(str(pk) for pk in batch_ids)}'[:255]
    elif purpose == PaymentTransaction.Purpose.WALLET:
        schematic = None
        plan = None
        try:
            amount = int(amount)
        except (TypeError, ValueError) as exc:
            raise PaymentError('مبلغ شارژ کیف پول نامعتبر است.') from exc
        if amount < MIN_WALLET_TOPUP:
            raise PaymentError(f'حداقل شارژ کیف پول {MIN_WALLET_TOPUP} تومان است.')
        description = f'Wallet top-up {amount}'[:255]
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
        schematic_ids=batch_ids,
        plan=plan,
        description=description,
        claim_token_hash=claim_token_hash,
        guest_account_created=guest_account_created,
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
    document cannot spawn an empty guest account.

    Returns (txn, payment_url, claim_token). The plaintext claim_token is
    returned once to the caller that started checkout and is stored only as
    HMAC. GET /verify/ never sees it and must not mint JWT.
    """
    try:
        schematic = Schematic.objects.get(pk=schematic_id)
    except Schematic.DoesNotExist as exc:
        raise PaymentError('شماتیک مورد نظر یافت نشد.') from exc
    if schematic.is_free or schematic.price <= 0:
        raise PaymentError('این شماتیک برای خرید تکی در دسترس نیست.')

    user, created = get_or_create_checkout_user(phone_number)
    raw_claim = generate_claim_token()
    txn, payment_url = create_payment_request(
        user=user,
        purpose=PaymentTransaction.Purpose.SCHEMATIC,
        schematic_id=schematic.pk,
        request=request,
        claim_token_hash=hash_claim_token(raw_claim),
        guest_account_created=created,
    )
    return txn, payment_url, raw_claim


def claim_guest_session(*, authority: str, claim_token: str) -> dict:
    """
    Issue JWT only when the caller proves the checkout-bound claim token.

    Conditions (all required):
    - transaction is PAID
    - HMAC matches
    - this checkout created the user (not a pre-existing guest/registered row)
    - the user still has no login password
    """
    try:
        txn = PaymentTransaction.objects.select_related('user').get(authority=authority)
    except PaymentTransaction.DoesNotExist as exc:
        raise PaymentError('تراکنش پرداخت یافت نشد.') from exc

    if txn.status != PaymentTransaction.Status.PAID:
        raise PaymentError('پرداخت هنوز تایید نشده است.')

    user = txn.user
    allowed = (
        claim_token_matches(txn.claim_token_hash, claim_token)
        and txn.guest_account_created
        and user.is_guest
    )
    if not allowed:
        raise PaymentClaimDenied('امکان صدور نشست برای این تراکنش وجود ندارد.')

    if txn.claimed_at is None:
        txn.claimed_at = timezone.now()
        txn.save(update_fields=['claimed_at'])

    payload = {
        'user': public_account_payload(user),
        'paid': True,
        'detail': 'نشست با موفقیت صادر شد.',
    }
    payload.update(issue_jwt_for(user))
    return payload


def parse_gateway_callback(params) -> tuple[str, bool]:
    """
    Read Zarinpal-style Authority/Status from a query mapping.

    Empty Status is treated as OK so API clients can poll with authority only.
    """
    get = params.get
    authority = str(get('Authority') or get('authority') or '').strip()
    raw_status = str(get('Status') or get('status') or '')
    gateway_ok = raw_status.upper() in ('OK', 'SUCCESS', '')
    if raw_status.upper() in ('NOK', 'FAILED', 'CANCELED', 'CANCELLED'):
        gateway_ok = False
    return authority, gateway_ok


def _default_callback(request) -> str:
    """Gateway browsers return to the HTML result page, not the JSON verify API."""
    if request is None:
        return HTML_CALLBACK_PATH
    return request.build_absolute_uri(reverse('web:payment-callback'))


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
    if txn.purpose == PaymentTransaction.Purpose.SCHEMATIC:
        ids = txn.purchased_schematic_ids()
        if not ids:
            raise PaymentError('تراکنش هدف مشخصی برای فعال‌سازی ندارد.')
        found = {
            item.pk: item
            for item in Schematic.objects.filter(pk__in=ids)
        }
        granted = 0
        for pk in ids:
            schematic = found.get(pk)
            if schematic is None:
                continue
            fulfill_schematic_purchase(txn.user, schematic, price_paid=schematic.price)
            granted += 1
        if granted == 0:
            raise PaymentError('تراکنش هدف مشخصی برای فعال‌سازی ندارد.')
    elif txn.purpose == PaymentTransaction.Purpose.WALLET:
        credit_wallet(txn.user, txn.amount)
    elif txn.purpose == PaymentTransaction.Purpose.SUBSCRIPTION:
        raise PaymentError(SUBSCRIPTION_RETIRED_MESSAGE)
    else:
        raise PaymentError('تراکنش هدف مشخصی برای فعال‌سازی ندارد.')


def credit_wallet(user, amount) -> None:
    """Add Tomans to the user's wallet. Caller must be inside an atomic block when verifying."""
    from django.contrib.auth import get_user_model

    User = get_user_model()
    locked = User.objects.select_for_update().get(pk=user.pk)
    locked.wallet_balance = (locked.wallet_balance or 0) + amount
    locked.save(update_fields=['wallet_balance'])


def pay_schematic_from_wallet(user, schematic_id):
    """Spend wallet balance on a single schematic. No gateway round-trip."""
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
    from django.contrib.auth import get_user_model

    User = get_user_model()
    with transaction.atomic():
        locked = User.objects.select_for_update().get(pk=user.pk)
        if locked.wallet_balance < amount:
            raise PaymentError('موجودی کیف پول کافی نیست.')
        locked.wallet_balance -= amount
        locked.save(update_fields=['wallet_balance'])
        return fulfill_schematic_purchase(locked, schematic, price_paid=amount)
