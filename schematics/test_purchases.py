"""
API tests for single-copy schematic purchases.

HTTP POST never writes SchematicPurchase — that row is created only after a
successful payment verification (see payments app). This module covers
validation, duplicate ownership, listing, and the fulfill() helper.
"""

from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework import status

from schematics.factories import SchematicFactory, SchematicPurchaseFactory, UserFactory
from schematics.models import SchematicPurchase
from schematics.services import (
    AlreadyPurchased,
    SchematicNotPurchasable,
    assert_schematic_purchasable,
    fulfill_schematic_purchase,
)


@pytest.mark.django_db
class TestSchematicPurchaseService:
    def test_fulfill_grants_download_access(self):
        user = UserFactory()
        schematic = SchematicFactory(is_free=False, price=120000, requires_subscription=True)

        purchase, created = fulfill_schematic_purchase(user, schematic)

        assert created is True
        assert purchase.price_paid == 120000
        assert schematic.user_can_download(user) is True

    def test_fulfill_is_idempotent_on_second_call(self):
        user = UserFactory()
        schematic = SchematicFactory(is_free=False, price=90000)
        first, _ = fulfill_schematic_purchase(user, schematic)
        second, created = fulfill_schematic_purchase(user, schematic)

        assert created is False
        assert first.pk == second.pk
        assert SchematicPurchase.objects.filter(user=user, schematic=schematic).count() == 1

    def test_assert_purchasable_rejects_free_and_owned_rows(self):
        user = UserFactory()
        free = SchematicFactory(is_free=True, price=0)
        with pytest.raises(SchematicNotPurchasable):
            assert_schematic_purchasable(user, free)

        paid = SchematicFactory(is_free=False, price=50000)
        SchematicPurchaseFactory(user=user, schematic=paid)
        with pytest.raises(AlreadyPurchased):
            assert_schematic_purchasable(user, paid)


@pytest.mark.django_db
class TestSchematicPurchaseAPI:
    def test_anonymous_cannot_list_or_checkout(self, api_client):
        list_url = reverse('schematics:purchase-list')
        assert api_client.get(list_url).status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )
        assert api_client.post(list_url, {'schematic_id': 1}).status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

    def test_list_returns_only_the_current_user_purchases(self, api_client):
        owner = UserFactory()
        other = UserFactory()
        mine = SchematicPurchaseFactory(user=owner)
        SchematicPurchaseFactory(user=other)
        api_client.force_authenticate(user=owner)

        response = api_client.get(reverse('schematics:purchase-list'))

        assert response.status_code == status.HTTP_200_OK
        ids = [row['id'] for row in response.data]
        assert ids == [mine.pk]

    def test_checkout_rejects_free_schematic_without_creating_a_row(self, api_client):
        user = UserFactory()
        schematic = SchematicFactory(is_free=True, price=0)
        api_client.force_authenticate(user=user)

        response = api_client.post(
            reverse('schematics:purchase-list'),
            {'schematic_id': schematic.pk},
            format='json',
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert SchematicPurchase.objects.filter(user=user).count() == 0

    def test_checkout_rejects_duplicate_ownership(self, api_client):
        user = UserFactory()
        schematic = SchematicFactory(is_free=False, price=80000)
        SchematicPurchaseFactory(user=user, schematic=schematic)
        api_client.force_authenticate(user=user)

        response = api_client.post(
            reverse('schematics:purchase-list'),
            {'schematic_id': schematic.pk},
            format='json',
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        assert SchematicPurchase.objects.filter(user=user, schematic=schematic).count() == 1

    def test_checkout_does_not_grant_access_before_payment(self, api_client):
        """Security: POST /purchases/ must not write a ledger row (payment verify does)."""
        user = UserFactory()
        schematic = SchematicFactory(is_free=False, price=150000, requires_subscription=True)
        api_client.force_authenticate(user=user)

        response = api_client.post(
            reverse('schematics:purchase-list'),
            {'schematic_id': schematic.pk},
            format='json',
        )

        assert response.status_code == status.HTTP_402_PAYMENT_REQUIRED
        assert response.data['schematic_id'] == schematic.pk
        assert int(response.data['amount']) == 150000
        assert SchematicPurchase.objects.filter(user=user, schematic=schematic).exists() is False
        assert schematic.user_can_download(user) is False

    def test_unknown_schematic_returns_400(self, api_client):
        user = UserFactory()
        api_client.force_authenticate(user=user)
        response = api_client.post(
            reverse('schematics:purchase-list'),
            {'schematic_id': 999999},
            format='json',
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_schematic_purchase_is_registered_in_admin():
    from django.contrib import admin

    from schematics.admin import SchematicPurchaseAdmin
    from schematics.models import SchematicPurchase

    assert SchematicPurchase in admin.site._registry
    model_admin = admin.site._registry[SchematicPurchase]
    assert isinstance(model_admin, SchematicPurchaseAdmin)
    assert 'user__phone_number' in model_admin.search_fields
    assert 'created_at' in model_admin.list_filter
