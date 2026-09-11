"""
Payment gateway contract tests (mock adapter).

Real Zarinpal/IDPay adapters must keep this same request/verify shape so the
views never depend on a vendor SDK.
"""

from __future__ import annotations

import pytest
from django.test import override_settings

from payments.gateways import MockGateway, PaymentVerifyResult, get_gateway


class TestMockGateway:
    def test_request_returns_zarinpal_shaped_authority_and_url(self):
        gateway = MockGateway()
        result = gateway.request_payment(
            amount=150000,
            description='S24 schematic',
            callback_url='http://testserver/api/v1/payments/verify/',
        )
        assert result.authority.startswith('MOCK')
        assert result.payment_url.endswith(result.authority)
        assert 'StartPay' in result.payment_url

    def test_verify_success_by_default(self):
        gateway = MockGateway()
        requested = gateway.request_payment(amount=1, description='x', callback_url='/')
        verified = gateway.verify_payment(authority=requested.authority, amount=1)
        assert verified.success is True
        assert verified.ref_id

    @override_settings(PAYMENT_MOCK_SUCCESS=False)
    def test_verify_can_be_forced_to_fail_for_tests(self):
        gateway = MockGateway()
        requested = gateway.request_payment(amount=1, description='x', callback_url='/')
        verified = gateway.verify_payment(authority=requested.authority, amount=1)
        assert verified.success is False
        assert isinstance(verified, PaymentVerifyResult)

    def test_get_gateway_defaults_to_mock(self):
        assert isinstance(get_gateway(), MockGateway)
