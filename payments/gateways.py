"""
Gateway adapters.

Every adapter exposes request_payment() / verify_payment() with the same
dataclasses. Views never import Zarinpal or IDPay SDKs directly — swap the
class via settings.PAYMENT_GATEWAY.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


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


class MockGateway(PaymentGateway):
    """
    Local/sandbox gateway.

    request_payment mints a MOCK… authority and a StartPay-style URL (same path
    shape Zarinpal uses). verify_payment succeeds unless PAYMENT_MOCK_SUCCESS
    is False, so tests can exercise the decline path without HTTP.
    """

    name = 'mock'

    def request_payment(self, *, amount, description: str, callback_url: str, extra=None) -> PaymentRequestResult:
        authority = 'MOCK' + uuid4().hex[:32].upper()
        base = getattr(
            settings,
            'PAYMENT_START_URL_TEMPLATE',
            'https://sandbox.zarinpal.com/pg/StartPay/{authority}',
        )
        return PaymentRequestResult(
            authority=authority,
            payment_url=base.format(authority=authority),
        )

    def verify_payment(self, *, authority: str, amount) -> PaymentVerifyResult:
        if not getattr(settings, 'PAYMENT_MOCK_SUCCESS', True):
            return PaymentVerifyResult(success=False, message='Mock gateway declined the payment.')
        if not str(authority).startswith('MOCK'):
            return PaymentVerifyResult(success=False, message='Unknown mock authority.')
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
    Wire HTTP here when MERCHANT_ID is provisioned; until then use MockGateway.
    """

    name = 'zarinpal'

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

    name = getattr(settings, 'PAYMENT_GATEWAY', 'mock')
    if name == 'mock' and not mock_gateway_allowed(debug=bool(getattr(settings, 'DEBUG', False))):
        raise ImproperlyConfigured(
            'PAYMENT_GATEWAY=mock is not allowed when DEBUG=False. '
            'Use a live adapter or enable DEBUG for local development.'
        )
    try:
        return _REGISTRY[name]()
    except KeyError as exc:
        raise ImproperlyConfigured(f'Unknown PAYMENT_GATEWAY={name!r}') from exc
