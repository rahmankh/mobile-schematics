"""
Payment gateway contract tests (mock adapter).

Real Zarinpal/IDPay adapters must keep this same request/verify shape so the
views never depend on a vendor SDK.
"""

from __future__ import annotations

import pytest
from django.test import override_settings

from payments.gateways import (
    MockGateway,
    PaymentVerifyResult,
    get_gateway,
    is_recognized_mock_authority,
    mint_sandbox_authority,
)


class TestMockGateway:
    def test_request_returns_sandbox_authority_and_on_site_verify_url(self):
        gateway = MockGateway()
        result = gateway.request_payment(
            amount=150000,
            description='S24 schematic',
            callback_url='http://testserver/api/v1/payments/verify/',
        )
        assert result.authority.startswith('S.')
        assert len(result.authority) == 34
        assert 'Authority=' + result.authority in result.payment_url
        assert 'Status=OK' in result.payment_url
        assert 'zarinpal.com' not in result.payment_url
        assert result.payment_url.startswith('http://testserver/api/v1/payments/verify/')

    def test_minted_authority_is_recognized(self):
        authority = mint_sandbox_authority()
        assert is_recognized_mock_authority(authority) is True
        assert is_recognized_mock_authority('MOCK' + 'A' * 32) is True
        assert is_recognized_mock_authority('A.ABC') is True
        assert is_recognized_mock_authority('not-a-gateway-code') is False

    def test_verify_accepts_legacy_mock_prefix(self):
        gateway = MockGateway()
        verified = gateway.verify_payment(authority='MOCKDEADBEEF', amount=150000)
        assert verified.success is True

    def test_verify_rejects_unprefixed_authority(self):
        gateway = MockGateway()
        verified = gateway.verify_payment(authority='DEADBEEF', amount=150000)
        assert verified.success is False
        assert 'S.' in verified.message

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

    @override_settings(PAYMENT_START_URL_TEMPLATE='https://pay.local/start/{authority}')
    def test_custom_non_zarinpal_start_url_is_honored(self):
        gateway = MockGateway()
        result = gateway.request_payment(amount=1, description='x', callback_url='/cb')
        assert result.payment_url == f'https://pay.local/start/{result.authority}'

    def test_get_gateway_defaults_to_mock(self):
        assert isinstance(get_gateway(), MockGateway)
