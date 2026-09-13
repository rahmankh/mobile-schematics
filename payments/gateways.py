"""
Gateway adapters.

Every adapter exposes request_payment() / verify_payment() with the same
dataclasses. Views never import Zarinpal or IDPay SDKs directly — swap the
class via settings.PAYMENT_GATEWAY.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

# Zarinpal sandbox authorities are `S.` + 32 hex chars. Production uses `A.`.
# Legacy mock rows used a MOCK prefix; verify still accepts those.
SANDBOX_AUTHORITY_PREFIX = 'S.'
_MOCK_AUTHORITY_PREFIXES = (SANDBOX_AUTHORITY_PREFIX, 'A.', 'MOCK')
_ZARINPAL_HOST_MARKERS = ('zarinpal.com', 'zarinpal.ir')
# Browser return path used when no callback_url is supplied. JSON verify stays at
# /api/v1/payments/verify/ for programmatic clients.
HTML_CALLBACK_PATH = '/payments/callback/'


@dataclass(frozen=True)
class PaymentRequestResult:
    """Zarinpal-shaped start-pay payload: opaque authority + browser URL."""

    authority: str
    payment_url: str


@dataclass(frozen=True)
class PaymentVerifyResult:
    """Result of confirming a previously issued authority."""

    success: bool
    ref_id: str = ''
    amount: int | None = None
    message: str = ''


class PaymentGateway:
    """Interface both the mock and future live adapters implement."""

    name = 'base'

    def request_payment(self, *, amount, description: str, callback_url: str, extra=None) -> PaymentRequestResult:
        raise NotImplementedError

    def verify_payment(self, *, authority: str, amount) -> PaymentVerifyResult:
        raise NotImplementedError


def mint_sandbox_authority() -> str:
    """Return a Zarinpal-sandbox-shaped authority (`S.` + 32 hex)."""
    return f'{SANDBOX_AUTHORITY_PREFIX}{uuid4().hex.upper()}'


def is_recognized_mock_authority(authority: str) -> bool:
    """True when verify should treat this handle as a local/sandbox mock token."""
    value = str(authority or '')
    return value.startswith(_MOCK_AUTHORITY_PREFIXES)


def _append_query(url: str, **params: str) -> str:
    parts = urlsplit(url or HTML_CALLBACK_PATH)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update(params)
    path = parts.path or HTML_CALLBACK_PATH
    return urlunsplit((parts.scheme, parts.netloc, path, urlencode(query), parts.fragment))


def _mock_payment_url(*, authority: str, callback_url: str) -> str:
    """
    Build the browser hop after request_payment.

    Real Zarinpal sandbox StartPay URLs reject authorities they did not issue
    (validation error: sandbox codes must start with S.). Mock checkout therefore
    returns to our verify callback with Status=OK instead of opening zarinpal.com.
    An explicit non-Zarinpal PAYMENT_START_URL_TEMPLATE is still honored.
    """
    template = str(getattr(settings, 'PAYMENT_START_URL_TEMPLATE', '') or '')
    if template and not any(marker in template.lower() for marker in _ZARINPAL_HOST_MARKERS):
        return template.format(authority=authority)
    return _append_query(
        callback_url or HTML_CALLBACK_PATH,
        Authority=authority,
        Status='OK',
    )


class MockGateway(PaymentGateway):
    """
    Local/sandbox gateway.

    request_payment mints a Zarinpal-sandbox-shaped `S.…` authority and a URL
    that returns to our verify callback. Hitting sandbox.zarinpal.com with a
    locally minted code fails their authority check, so mock never does that.

    verify_payment succeeds unless PAYMENT_MOCK_SUCCESS is False, so tests can
    exercise the decline path without HTTP. LIVE_READY is False.
    """

    name = 'mock'
    LIVE_READY = False

    def request_payment(self, *, amount, description: str, callback_url: str, extra=None) -> PaymentRequestResult:
        authority = mint_sandbox_authority()
        return PaymentRequestResult(
            authority=authority,
            payment_url=_mock_payment_url(authority=authority, callback_url=callback_url),
        )

    def verify_payment(self, *, authority: str, amount) -> PaymentVerifyResult:
        if not getattr(settings, 'PAYMENT_MOCK_SUCCESS', True):
            return PaymentVerifyResult(success=False, message='Mock gateway declined the payment.')
        if not is_recognized_mock_authority(authority):
            return PaymentVerifyResult(
                success=False,
                message='کد authority نامعتبر است. در حالت آزمایشی باید با S. شروع شود.',
            )
        # Deterministic-enough tracking code for receipts / admin search.
        ref = str(abs(hash(authority)) % 10_000_000)
        return PaymentVerifyResult(success=True, ref_id=ref, amount=int(amount))


class ZarinpalGateway(PaymentGateway):
    """
    Live Zarinpal adapter placeholder.

    Expected SOAP/REST mapping (v4):
      request → POST {merchant_id, amount, description, callback_url} → authority
      pay     → https://www.zarinpal.com/pg/StartPay/{authority}
      verify  → POST {merchant_id, amount, authority} → ref_id
    Wire HTTP here when MERCHANT_ID is provisioned; until then LIVE_READY stays
    False and production boot / get_gateway() refuse this adapter.
    """

    name = 'zarinpal'
    LIVE_READY = False

    def request_payment(self, *, amount, description: str, callback_url: str, extra=None) -> PaymentRequestResult:
        raise ImproperlyConfigured(
            'Zarinpal is not wired yet. Set PAYMENT_GATEWAY=mock for local development.'
        )

    def verify_payment(self, *, authority: str, amount) -> PaymentVerifyResult:
        raise ImproperlyConfigured(
            'Zarinpal is not wired yet. Set PAYMENT_GATEWAY=mock for local development.'
        )


class IDPayGateway(PaymentGateway):
    """
    Live IDPay adapter placeholder.

    Expected REST mapping:
      request → POST {order_id, amount, callback} with X-API-KEY → id + link
      verify  → POST {id, order_id}
    """

    name = 'idpay'
    LIVE_READY = False

    def request_payment(self, *, amount, description: str, callback_url: str, extra=None) -> PaymentRequestResult:
        raise ImproperlyConfigured(
            'IDPay is not wired yet. Set PAYMENT_GATEWAY=mock for local development.'
        )

    def verify_payment(self, *, authority: str, amount) -> PaymentVerifyResult:
        raise ImproperlyConfigured(
            'IDPay is not wired yet. Set PAYMENT_GATEWAY=mock for local development.'
        )


_REGISTRY = {
    'mock': MockGateway,
    'zarinpal': ZarinpalGateway,
    'idpay': IDPayGateway,
}


def get_gateway() -> PaymentGateway:
    """Instantiate the adapter named in settings.PAYMENT_GATEWAY (default mock)."""
    from config.security import mock_gateway_allowed

    name = str(getattr(settings, 'PAYMENT_GATEWAY', 'mock')).strip().lower()
    debug = bool(getattr(settings, 'DEBUG', False))
    allow_dev = mock_gateway_allowed(debug=debug)

    if name == 'mock':
        if not allow_dev:
            raise ImproperlyConfigured(
                'PAYMENT_GATEWAY=mock is not allowed when DEBUG=False. '
                'Use a live adapter or enable DEBUG for local development.'
            )
        return MockGateway()

    try:
        adapter_cls = _REGISTRY[name]
    except KeyError as exc:
        raise ImproperlyConfigured(f'Unknown PAYMENT_GATEWAY={name!r}') from exc

    if name == 'zarinpal' and not str(getattr(settings, 'PAYMENT_ZARINPAL_MERCHANT_ID', '')).strip():
        if not allow_dev:
            raise ImproperlyConfigured(
                'PAYMENT_ZARINPAL_MERCHANT_ID is required when PAYMENT_GATEWAY=zarinpal.'
            )
    if name == 'idpay' and not str(getattr(settings, 'PAYMENT_IDPAY_API_KEY', '')).strip():
        if not allow_dev:
            raise ImproperlyConfigured(
                'PAYMENT_IDPAY_API_KEY is required when PAYMENT_GATEWAY=idpay.'
            )

    if not getattr(adapter_cls, 'LIVE_READY', False) and not allow_dev:
        raise ImproperlyConfigured(
            f'PAYMENT_GATEWAY={name} is still a stub and cannot take live charges.'
        )
    return adapter_cls()
