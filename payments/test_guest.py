"""
Guest checkout: buy one schematic with only a mobile number (no password).

Invariants:
- PENDING payment does not grant download.
- GET /verify/ fulfills payment and never mints JWT.
- JWT is issued only by POST /claim/ with the HMAC-bound claim_token, and only
  when this checkout created the guest row (no takeover of existing guests).
- Guest responses do not report whether the phone is already registered.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework_simplejwt.tokens import AccessToken

from payments.claims import claim_token_matches, hash_claim_token
from payments.models import PaymentTransaction
from schematics.factories import SchematicFactory, SchematicFileFactory, SchematicPurchaseFactory, UserFactory
from schematics.models import SchematicPurchase

User = get_user_model()

SESSION_LEAK_KEYS = (
    'access',
    'refresh',
    'account_status',
    'is_guest',
    'login_required',
    'phone_number',
    'guest_account_created',
    'claim_token_hash',
)


@pytest.fixture
def guest_url():
    return reverse('payments:guest-checkout')


@pytest.fixture
def verify_url():
    return reverse('payments:payment-verify')


@pytest.fixture
def claim_url():
    return reverse('payments:payment-claim')


def _assert_no_session_leak(payload: dict) -> None:
    for key in SESSION_LEAK_KEYS:
        assert key not in payload


@pytest.mark.django_db
class TestGuestCheckoutRequest:
    def test_creates_guest_user_and_pending_payment(self, api_client, guest_url):
        schematic = SchematicFactory(is_free=False, price=175000)

        response = api_client.post(
            guest_url,
            {'phone_number': '09127770001', 'schematic_id': schematic.pk},
            format='json',
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['payment_url']
        assert response.data['authority']
        assert response.data['claim_token']
        assert int(response.data['amount']) == 175000
        _assert_no_session_leak(response.data)
        user = User.objects.get(phone_number='09127770001')
        assert user.is_guest is True
        txn = PaymentTransaction.objects.get(authority=response.data['authority'])
        assert txn.user_id == user.id
        assert txn.status == PaymentTransaction.Status.PENDING
        assert txn.guest_account_created is True
        assert txn.claim_token_hash
        assert txn.claim_token_hash != response.data['claim_token']
        assert claim_token_matches(txn.claim_token_hash, response.data['claim_token'])
        assert SchematicPurchase.objects.filter(user=user, schematic=schematic).exists() is False
        assert schematic.user_can_download(user) is False

    def test_normalizes_plus_98_phone(self, api_client, guest_url):
        schematic = SchematicFactory(is_free=False, price=50000)

        response = api_client.post(
            guest_url,
            {'phone_number': '+989127770002', 'schematic_id': schematic.pk},
            format='json',
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert User.objects.filter(phone_number='09127770002').exists()

    def test_rejects_invalid_phone(self, api_client, guest_url):
        schematic = SchematicFactory(is_free=False, price=50000)
        response = api_client.post(
            guest_url,
            {'phone_number': '12345', 'schematic_id': schematic.pk},
            format='json',
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_rejects_free_schematic(self, api_client, guest_url):
        schematic = SchematicFactory(is_free=True, price=0)
        response = api_client.post(
            guest_url,
            {'phone_number': '09127770003', 'schematic_id': schematic.pk},
            format='json',
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert User.objects.filter(phone_number='09127770003').exists() is False

    def test_existing_registered_response_matches_new_guest_shape(self, api_client, guest_url):
        existing = UserFactory(phone_number='09127770004', password='StrongPassword@123')
        schematic = SchematicFactory(is_free=False, price=80000)

        response = api_client.post(
            guest_url,
            {'phone_number': '09127770004', 'schematic_id': schematic.pk},
            format='json',
        )

        assert response.status_code == status.HTTP_201_CREATED
        _assert_no_session_leak(response.data)
        assert 'claim_token' in response.data
        assert User.objects.filter(phone_number='09127770004').count() == 1
        txn = PaymentTransaction.objects.get(authority=response.data['authority'])
        assert txn.user_id == existing.id
        assert txn.guest_account_created is False

    def test_existing_guest_response_does_not_reveal_account_state(self, api_client, guest_url):
        guest = User.objects.create_user(phone_number='09127770005', password=None)
        schematic = SchematicFactory(is_free=False, price=80000)

        response = api_client.post(
            guest_url,
            {'phone_number': '09127770005', 'schematic_id': schematic.pk},
            format='json',
        )

        assert response.status_code == status.HTTP_201_CREATED
        _assert_no_session_leak(response.data)
        assert User.objects.filter(phone_number='09127770005').count() == 1
        txn = PaymentTransaction.objects.get(authority=response.data['authority'])
        assert txn.user_id == guest.id
        assert txn.guest_account_created is False

    def test_conflict_when_phone_already_owns_schematic(self, api_client, guest_url):
        user = UserFactory(phone_number='09127770006')
        schematic = SchematicFactory(is_free=False, price=90000)
        SchematicPurchaseFactory(user=user, schematic=schematic)

        response = api_client.post(
            guest_url,
            {'phone_number': '09127770006', 'schematic_id': schematic.pk},
            format='json',
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        assert 'account_status' not in response.data
        assert PaymentTransaction.objects.filter(user=user).count() == 0

    def test_unknown_schematic_is_400(self, api_client, guest_url):
        response = api_client.post(
            guest_url,
            {'phone_number': '09127770007', 'schematic_id': 999999},
            format='json',
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestGuestCheckoutVerifyAndClaim:
    def test_verify_fulfills_but_does_not_mint_jwt(self, api_client, guest_url, verify_url):
        schematic = SchematicFactory(is_free=False, price=120000, requires_subscription=True)
        started = api_client.post(
            guest_url,
            {'phone_number': '09127770008', 'schematic_id': schematic.pk},
            format='json',
        )
        response = api_client.get(
            verify_url,
            {'Authority': started.data['authority'], 'Status': 'OK'},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data['paid'] is True
        _assert_no_session_leak(response.data)
        assert 'claim_token' not in response.data
        user = User.objects.get(phone_number='09127770008')
        assert SchematicPurchase.objects.filter(user=user, schematic=schematic).exists()
        assert schematic.user_can_download(user) is True

    def test_new_guest_can_claim_jwt_and_download(
        self, api_client, guest_url, verify_url, claim_url
    ):
        schematic = SchematicFactory(is_free=False, price=120000, requires_subscription=True)
        started = api_client.post(
            guest_url,
            {'phone_number': '09127770011', 'schematic_id': schematic.pk},
            format='json',
        )
        api_client.get(verify_url, {'Authority': started.data['authority'], 'Status': 'OK'})

        claimed = api_client.post(
            claim_url,
            {
                'authority': started.data['authority'],
                'claim_token': started.data['claim_token'],
            },
            format='json',
        )
        assert claimed.status_code == status.HTTP_200_OK
        assert claimed.data['access']
        assert claimed.data['refresh']
        assert claimed.data['user']['phone_number'] == '09127770011'
        token = AccessToken(claimed.data['access'])
        user = User.objects.get(phone_number='09127770011')
        assert int(token['user_id']) == user.pk

        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {claimed.data["access"]}')
        schematic_file = SchematicFileFactory(schematic=schematic)
        download = api_client.get(
            reverse('schematics:schematic-file-download', kwargs={'pk': schematic_file.pk})
        )
        assert download.status_code == status.HTTP_200_OK

        set_password = api_client.post(
            reverse('accounts:set-password'),
            {'password': 'StrongPassword@123', 'password_confirm': 'StrongPassword@123'},
            format='json',
        )
        assert set_password.status_code == status.HTTP_200_OK

    def test_existing_guest_cannot_take_over_via_claim(
        self, api_client, guest_url, verify_url, claim_url
    ):
        victim = User.objects.create_user(phone_number='09127770012', password=None)
        prior = SchematicFactory(is_free=False, price=50000)
        SchematicPurchaseFactory(user=victim, schematic=prior, price_paid=50000)
        schematic = SchematicFactory(is_free=False, price=110000)

        started = api_client.post(
            guest_url,
            {'phone_number': '09127770012', 'schematic_id': schematic.pk},
            format='json',
        )
        api_client.get(verify_url, {'Authority': started.data['authority'], 'Status': 'OK'})
        claimed = api_client.post(
            claim_url,
            {
                'authority': started.data['authority'],
                'claim_token': started.data['claim_token'],
            },
            format='json',
        )

        assert claimed.status_code == status.HTTP_403_FORBIDDEN
        assert 'access' not in claimed.data
        assert SchematicPurchase.objects.filter(user=victim, schematic=schematic).exists()
        victim.refresh_from_db()
        assert victim.is_guest is True
        assert victim.has_usable_password() is False

    def test_registered_verify_grants_purchase_without_jwt(
        self, api_client, guest_url, verify_url, claim_url
    ):
        UserFactory(phone_number='09127770009', password='StrongPassword@123')
        schematic = SchematicFactory(is_free=False, price=110000)
        started = api_client.post(
            guest_url,
            {'phone_number': '09127770009', 'schematic_id': schematic.pk},
            format='json',
        )
        response = api_client.get(
            verify_url,
            {'Authority': started.data['authority'], 'Status': 'OK'},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data['paid'] is True
        _assert_no_session_leak(response.data)
        claimed = api_client.post(
            claim_url,
            {
                'authority': started.data['authority'],
                'claim_token': started.data['claim_token'],
            },
            format='json',
        )
        assert claimed.status_code == status.HTTP_403_FORBIDDEN
        assert 'access' not in claimed.data
        user = User.objects.get(phone_number='09127770009')
        assert SchematicPurchase.objects.filter(user=user, schematic=schematic).exists()

    def test_wrong_claim_token_is_denied(self, api_client, guest_url, verify_url, claim_url):
        schematic = SchematicFactory(is_free=False, price=90000)
        started = api_client.post(
            guest_url,
            {'phone_number': '09127770013', 'schematic_id': schematic.pk},
            format='json',
        )
        api_client.get(verify_url, {'Authority': started.data['authority'], 'Status': 'OK'})
        claimed = api_client.post(
            claim_url,
            {
                'authority': started.data['authority'],
                'claim_token': 'not-the-real-token',
            },
            format='json',
        )
        assert claimed.status_code == status.HTTP_403_FORBIDDEN
        assert 'access' not in claimed.data

    def test_claim_before_verify_is_rejected(self, api_client, guest_url, claim_url):
        schematic = SchematicFactory(is_free=False, price=90000)
        started = api_client.post(
            guest_url,
            {'phone_number': '09127770014', 'schematic_id': schematic.pk},
            format='json',
        )
        claimed = api_client.post(
            claim_url,
            {
                'authority': started.data['authority'],
                'claim_token': started.data['claim_token'],
            },
            format='json',
        )
        assert claimed.status_code == status.HTTP_400_BAD_REQUEST
        assert 'access' not in claimed.data

    def test_nok_guest_callback_does_not_fulfill(self, api_client, guest_url, verify_url):
        schematic = SchematicFactory(is_free=False, price=60000)
        started = api_client.post(
            guest_url,
            {'phone_number': '09127770010', 'schematic_id': schematic.pk},
            format='json',
        )
        response = api_client.get(
            verify_url,
            {'Authority': started.data['authority'], 'Status': 'NOK'},
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        user = User.objects.get(phone_number='09127770010')
        assert SchematicPurchase.objects.filter(user=user).count() == 0
        _assert_no_session_leak(response.data)


def test_claim_token_hmac_is_not_plaintext():
    token = 'plain-claim-token-value'
    digest = hash_claim_token(token)
    assert digest != token
    assert len(digest) == 64
    assert claim_token_matches(digest, token) is True
    assert claim_token_matches(digest, 'other') is False
    assert claim_token_matches('', token) is False
