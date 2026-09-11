"""
Guest checkout: buy one schematic with only a mobile number (no password).

Invariants:
- PENDING payment does not grant download.
- A new phone creates a guest user (unusable password) and JWT is issued on verify.
- An existing registered account receives the purchase but never a session hijack JWT.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status

from payments.models import PaymentTransaction
from schematics.factories import SchematicFactory, SchematicPurchaseFactory, UserFactory
from schematics.models import SchematicPurchase

User = get_user_model()


@pytest.fixture
def guest_url():
    return reverse('payments:guest-checkout')


@pytest.fixture
def verify_url():
    return reverse('payments:payment-verify')


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
        assert int(response.data['amount']) == 175000
        assert response.data['account_status'] == 'created'
        user = User.objects.get(phone_number='09127770001')
        assert user.is_guest is True
        txn = PaymentTransaction.objects.get(authority=response.data['authority'])
        assert txn.user_id == user.id
        assert txn.status == PaymentTransaction.Status.PENDING
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

    def test_links_existing_registered_user_without_creating_another(self, api_client, guest_url):
        existing = UserFactory(phone_number='09127770004', password='StrongPassword@123')
        schematic = SchematicFactory(is_free=False, price=80000)

        response = api_client.post(
            guest_url,
            {'phone_number': '09127770004', 'schematic_id': schematic.pk},
            format='json',
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['account_status'] == 'existing_registered'
        assert User.objects.filter(phone_number='09127770004').count() == 1
        txn = PaymentTransaction.objects.get(authority=response.data['authority'])
        assert txn.user_id == existing.id

    def test_reuses_existing_guest_user(self, api_client, guest_url):
        guest = User.objects.create_user(phone_number='09127770005', password=None)
        schematic = SchematicFactory(is_free=False, price=80000)

        response = api_client.post(
            guest_url,
            {'phone_number': '09127770005', 'schematic_id': schematic.pk},
            format='json',
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['account_status'] == 'existing_guest'
        assert User.objects.filter(phone_number='09127770005').count() == 1
        txn = PaymentTransaction.objects.get(authority=response.data['authority'])
        assert txn.user_id == guest.id

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
        assert PaymentTransaction.objects.filter(user=user).count() == 0

    def test_unknown_schematic_is_400(self, api_client, guest_url):
        response = api_client.post(
            guest_url,
            {'phone_number': '09127770007', 'schematic_id': 999999},
            format='json',
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestGuestCheckoutVerify:
    def test_guest_verify_grants_purchase_and_jwt(self, api_client, guest_url, verify_url):
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
        assert response.data['is_guest'] is True
        assert response.data['login_required'] is False
        assert response.data['access']
        assert response.data['refresh']
        user = User.objects.get(phone_number='09127770008')
        assert SchematicPurchase.objects.filter(user=user, schematic=schematic).exists()
        assert schematic.user_can_download(user) is True

        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {response.data["access"]}')
        from schematics.factories import SchematicFileFactory

        schematic_file = SchematicFileFactory(schematic=schematic)
        download = api_client.get(
            reverse('schematics:schematic-file-download', kwargs={'pk': schematic_file.pk})
        )
        assert download.status_code == status.HTTP_200_OK

    def test_registered_verify_grants_purchase_without_jwt(
        self, api_client, guest_url, verify_url
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
        assert response.data['login_required'] is True
        assert response.data['is_guest'] is False
        assert 'access' not in response.data
        user = User.objects.get(phone_number='09127770009')
        assert SchematicPurchase.objects.filter(user=user, schematic=schematic).exists()

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
        assert 'access' not in response.data
