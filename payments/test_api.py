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
class TestBatchCheckoutAPI:
    def test_schematic_ids_sums_prices_and_mints_sandbox_authority(
        self, api_client, request_url
    ):
        user = UserFactory()
        first = SchematicFactory(is_free=False, price=80000, title='Board A')
        second = SchematicFactory(is_free=False, price=120000, title='Board B')
        api_client.force_authenticate(user=user)

        response = api_client.post(
            request_url,
            {
                'purpose': 'schematic',
                'schematic_ids': [first.pk, second.pk, first.pk],
            },
            format='json',
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert int(response.data['amount']) == 200000
        assert response.data['authority'].startswith('S.')
        assert sorted(response.data['schematic_ids']) == sorted([first.pk, second.pk])
        txn = PaymentTransaction.objects.get(authority=response.data['authority'])
        assert txn.status == PaymentTransaction.Status.PENDING
        assert txn.purchased_schematic_ids() == [first.pk, second.pk]
        assert SchematicPurchase.objects.filter(user=user).count() == 0

    def test_batch_skips_duplicates_owned_and_unpayable_items(
        self, api_client, request_url
    ):
        user = UserFactory()
        payable = SchematicFactory(is_free=False, price=50000)
        owned = SchematicFactory(is_free=False, price=90000)
        free = SchematicFactory(is_free=True, price=0)
        SchematicPurchaseFactory(user=user, schematic=owned)
        api_client.force_authenticate(user=user)

        response = api_client.post(
            request_url,
            {
                'purpose': 'schematic',
                'schematic_ids': [payable.pk, owned.pk, free.pk, 999999, payable.pk],
            },
            format='json',
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert int(response.data['amount']) == 50000
        assert response.data['schematic_ids'] == [payable.pk]
        assert SchematicPurchase.objects.filter(user=user).count() == 1

    def test_batch_verify_grants_view_access_for_every_item(
        self, api_client, request_url, verify_url
    ):
        user = UserFactory()
        first = SchematicFactory(is_free=False, price=40000)
        second = SchematicFactory(is_free=False, price=60000)
        api_client.force_authenticate(user=user)
        started = api_client.post(
            request_url,
            {'purpose': 'schematic', 'schematic_ids': [first.pk, second.pk]},
            format='json',
        )
        authority = started.data['authority']

        api_client.force_authenticate(user=None)
        response = api_client.get(verify_url, {'Authority': authority, 'Status': 'OK'})

        assert response.status_code == status.HTTP_200_OK
        assert response.data['paid'] is True
        assert sorted(response.data['schematic_ids']) == sorted([first.pk, second.pk])
        user = type(user).objects.get(pk=user.pk)
        first.refresh_from_db()
        second.refresh_from_db()
        assert SchematicPurchase.objects.filter(user=user).count() == 2
        assert first.user_can_view(user) is True
        assert second.user_can_view(user) is True
        assert first.user_can_download(user) is True
        prices = {
            row.schematic_id: int(row.price_paid)
            for row in SchematicPurchase.objects.filter(user=user)
        }
        assert prices[first.pk] == 40000
        assert prices[second.pk] == 60000

    def test_batch_pending_does_not_grant_access(self, api_client, request_url):
        user = UserFactory()
        first = SchematicFactory(is_free=False, price=40000)
        second = SchematicFactory(is_free=False, price=60000)
        api_client.force_authenticate(user=user)
        api_client.post(
            request_url,
            {'purpose': 'schematic', 'schematic_ids': [first.pk, second.pk]},
            format='json',
        )

        assert SchematicPurchase.objects.filter(user=user).count() == 0
        assert first.user_can_view(user) is False
        assert second.user_can_view(user) is False

    def test_batch_of_only_owned_items_conflicts(self, api_client, request_url):
        user = UserFactory()
        schematic = SchematicFactory(is_free=False, price=50000)
        SchematicPurchaseFactory(user=user, schematic=schematic)
        api_client.force_authenticate(user=user)

        response = api_client.post(
            request_url,
            {'purpose': 'schematic', 'schematic_ids': [schematic.pk, schematic.pk]},
            format='json',
        )

        assert response.status_code == status.HTTP_409_CONFLICT
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
