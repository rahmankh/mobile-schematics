"""
API tests for payment request/verify.

Invariant: SchematicPurchase and UserSubscription rows are written only after
the gateway verify() returns success. A pending request, a NOK callback, or a
declined verify must leave the commerce tables untouched.
"""

from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework import status

from payments.models import PaymentTransaction
from schematics.factories import PlanFactory, SchematicFactory, SchematicPurchaseFactory, UserFactory
from schematics.models import SchematicPurchase
from subscriptions.models import UserSubscription


@pytest.fixture
def request_url():
    return reverse('payments:payment-request')


@pytest.fixture
def verify_url():
    return reverse('payments:payment-verify')


@pytest.mark.django_db
class TestPaymentRequestAPI:
    def test_anonymous_cannot_start_payment(self, api_client, request_url):
        response = api_client.post(
            request_url,
            {'purpose': 'schematic', 'schematic_id': 1},
            format='json',
        )
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

    def test_schematic_request_creates_pending_transaction_but_not_a_purchase(
        self, api_client, request_url
    ):
        user = UserFactory()
        schematic = SchematicFactory(is_free=False, price=180000)
        api_client.force_authenticate(user=user)

        response = api_client.post(
            request_url,
            {'purpose': 'schematic', 'schematic_id': schematic.pk},
            format='json',
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['authority']
        assert response.data['payment_url']
        assert int(response.data['amount']) == 180000
        assert 'claim_token' not in response.data
        txn = PaymentTransaction.objects.get(authority=response.data['authority'])
        assert txn.status == PaymentTransaction.Status.PENDING
        assert txn.user_id == user.id
        assert SchematicPurchase.objects.filter(user=user, schematic=schematic).exists() is False
        assert schematic.user_can_download(user) is False

    def test_schematic_request_rejects_existing_owner(self, api_client, request_url):
        user = UserFactory()
        schematic = SchematicFactory(is_free=False, price=50000)
        SchematicPurchaseFactory(user=user, schematic=schematic)
        api_client.force_authenticate(user=user)

        response = api_client.post(
            request_url,
            {'purpose': 'schematic', 'schematic_id': schematic.pk},
            format='json',
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        assert PaymentTransaction.objects.filter(user=user).count() == 0

    def test_subscription_request_is_rejected(self, api_client, request_url):
        user = UserFactory()
        plan = PlanFactory(price=250000, duration_days=30)
        api_client.force_authenticate(user=user)

        response = api_client.post(
            request_url,
            {'purpose': 'subscription', 'plan_id': plan.pk},
            format='json',
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert UserSubscription.objects.filter(user=user).count() == 0
        assert PaymentTransaction.objects.filter(user=user).count() == 0


@pytest.mark.django_db
class TestPaymentVerifyAPI:
    def _start(self, api_client, request_url, user, payload):
        api_client.force_authenticate(user=user)
        return api_client.post(request_url, payload, format='json')

    def test_nok_callback_does_not_fulfill_schematic(
        self, api_client, request_url, verify_url
    ):
        user = UserFactory()
        schematic = SchematicFactory(is_free=False, price=90000)
        started = self._start(
            api_client,
            request_url,
            user,
            {'purpose': 'schematic', 'schematic_id': schematic.pk},
        )
        authority = started.data['authority']

        # Gateway callbacks are unauthenticated (browser redirect).
        api_client.force_authenticate(user=None)
        response = api_client.get(verify_url, {'Authority': authority, 'Status': 'NOK'})

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        txn = PaymentTransaction.objects.get(authority=authority)
        assert txn.status == PaymentTransaction.Status.CANCELED
        assert SchematicPurchase.objects.filter(user=user, schematic=schematic).exists() is False

    def test_failed_gateway_verify_does_not_fulfill(
        self, api_client, request_url, verify_url, settings
    ):
        settings.PAYMENT_MOCK_SUCCESS = False
        user = UserFactory()
        schematic = SchematicFactory(is_free=False, price=90000)
        started = self._start(
            api_client,
            request_url,
            user,
            {'purpose': 'schematic', 'schematic_id': schematic.pk},
        )

        api_client.force_authenticate(user=None)
        response = api_client.get(
            verify_url,
            {'Authority': started.data['authority'], 'Status': 'OK'},
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert SchematicPurchase.objects.filter(user=user).count() == 0
        txn = PaymentTransaction.objects.get(authority=started.data['authority'])
        assert txn.status == PaymentTransaction.Status.FAILED

    def test_successful_verify_creates_purchase_and_grants_download(
        self, api_client, request_url, verify_url
    ):
        user = UserFactory()
        schematic = SchematicFactory(is_free=False, price=120000, requires_subscription=True)
        started = self._start(
            api_client,
            request_url,
            user,
            {'purpose': 'schematic', 'schematic_id': schematic.pk},
        )
        authority = started.data['authority']

        api_client.force_authenticate(user=None)
        response = api_client.get(verify_url, {'Authority': authority, 'Status': 'OK'})

        assert response.status_code == status.HTTP_200_OK
        assert response.data['paid'] is True
        assert 'access' not in response.data
        assert 'refresh' not in response.data
        assert SchematicPurchase.objects.filter(user=user, schematic=schematic).exists()
        schematic.refresh_from_db()
        # user_can_download needs an authenticated user object
        user = type(user).objects.get(pk=user.pk)
        from django.contrib.auth.models import AnonymousUser  # noqa: F401

        assert schematic.user_can_download(user) is True
        txn = PaymentTransaction.objects.get(authority=authority)
        assert txn.status == PaymentTransaction.Status.PAID
        assert txn.ref_id
        assert txn.verified_at is not None

    def test_successful_verify_credits_wallet(self, api_client, request_url, verify_url):
        user = UserFactory(wallet_balance=0)
        started = self._start(
            api_client,
            request_url,
            user,
            {'purpose': 'wallet', 'amount': 100000},
        )

        response = api_client.get(
            verify_url,
            {'Authority': started.data['authority'], 'Status': 'OK'},
        )

        assert response.status_code == status.HTTP_200_OK
        user.refresh_from_db()
        assert user.wallet_balance == 100000

    def test_verify_is_idempotent_and_does_not_duplicate_purchase(
        self, api_client, request_url, verify_url
    ):
        user = UserFactory()
        schematic = SchematicFactory(is_free=False, price=70000)
        started = self._start(
            api_client,
            request_url,
            user,
            {'purpose': 'schematic', 'schematic_id': schematic.pk},
        )
        params = {'Authority': started.data['authority'], 'Status': 'OK'}
        first = api_client.get(verify_url, params)
        second = api_client.get(verify_url, params)

        assert first.status_code == status.HTTP_200_OK
        assert second.status_code == status.HTTP_200_OK
        assert SchematicPurchase.objects.filter(user=user, schematic=schematic).count() == 1

    def test_legacy_subscription_purchase_endpoint_is_gone(self, api_client):
        user = UserFactory()
        plan = PlanFactory(is_active=True, price=100000)
        api_client.force_authenticate(user=user)

        response = api_client.post(
            reverse('subscriptions:purchase-subscription'),
            {'plan_id': plan.pk},
            format='json',
        )

        assert response.status_code == status.HTTP_410_GONE
        assert UserSubscription.objects.filter(user=user).count() == 0


@pytest.mark.django_db
class TestWalletSpend:
    def test_wallet_pays_for_schematic_and_grants_download(self):
        from payments.services import pay_schematic_from_wallet

        user = UserFactory(wallet_balance=200000)
        schematic = SchematicFactory(is_free=False, price=120000)
        pay_schematic_from_wallet(user, schematic.pk)
        user.refresh_from_db()
        assert user.wallet_balance == 80000
        assert SchematicPurchase.objects.filter(user=user, schematic=schematic).exists()
        assert schematic.user_can_download(user) is True

    def test_wallet_pay_rejects_insufficient_balance(self):
        from payments.services import PaymentError, pay_schematic_from_wallet

        user = UserFactory(wallet_balance=1000)
        schematic = SchematicFactory(is_free=False, price=120000)
        with pytest.raises(PaymentError):
            pay_schematic_from_wallet(user, schematic.pk)
        user.refresh_from_db()
        assert user.wallet_balance == 1000
        assert schematic.user_can_download(user) is False
