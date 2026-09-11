"""
Authenticated profile/status dashboard: identity, active plan, and owned schematics.
"""

from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework import status

from schematics.factories import (
    SchematicPurchaseFactory,
    UserFactory,
    UserSubscriptionFactory,
)


@pytest.mark.django_db
class TestProfileDashboard:
    def test_profile_includes_subscription_and_purchases(self, api_client):
        user = UserFactory(
            phone_number='09125550001',
            first_name='Nima',
            last_name='Rezaei',
            repair_shop_name='Tabriz Shop',
        )
        sub = UserSubscriptionFactory(user=user)
        purchase = SchematicPurchaseFactory(user=user, price_paid=180000)
        SchematicPurchaseFactory()  # another technician; must not leak
        api_client.force_authenticate(user=user)

        response = api_client.get(reverse('accounts:profile'))

        assert response.status_code == status.HTTP_200_OK
        data = response.data
        assert data['phone_number'] == '09125550001'
        assert data['first_name'] == 'Nima'
        assert data['repair_shop_name'] == 'Tabriz Shop'
        assert data['is_guest'] is False
        assert data['has_active_subscription'] is True
        assert data['subscription']['id'] == sub.pk
        assert data['subscription']['plan_title'] == sub.plan.title
        assert data['purchase_count'] == 1
        ids = [row['id'] for row in data['purchases']]
        assert ids == [purchase.pk]
        assert data['purchases'][0]['schematic_title'] == purchase.schematic.title

    def test_profile_without_subscription_or_purchases(self, api_client):
        user = UserFactory()
        api_client.force_authenticate(user=user)

        response = api_client.get(reverse('accounts:profile'))

        assert response.status_code == status.HTTP_200_OK
        assert response.data['has_active_subscription'] is False
        assert response.data['subscription'] is None
        assert response.data['purchases'] == []
        assert response.data['purchase_count'] == 0

    def test_guest_profile_flags_is_guest(self, api_client):
        from django.contrib.auth import get_user_model

        user = get_user_model().objects.create_user(phone_number='09125550002', password=None)
        api_client.force_authenticate(user=user)

        response = api_client.get(reverse('accounts:profile'))

        assert response.status_code == status.HTTP_200_OK
        assert response.data['is_guest'] is True
        assert response.data['phone_number'] == '09125550002'
