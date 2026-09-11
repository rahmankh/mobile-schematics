"""
Auth API: Iranian phone register/login, guest accounts cannot password-login,
and authenticated guests can set a password to claim the account.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status

from schematics.factories import UserFactory

User = get_user_model()


@pytest.mark.django_db
class TestRegisterAndLogin:
    def test_register_normalizes_plus_98_phone(self, api_client):
        response = api_client.post(
            reverse('accounts:register'),
            {
                'phone_number': '+989123000111',
                'first_name': 'Sara',
                'last_name': 'Karimi',
                'repair_shop_name': 'Shiraz Repair',
                'password': 'StrongPassword@123',
                'password_confirm': 'StrongPassword@123',
            },
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert User.objects.filter(phone_number='09123000111').exists()

    def test_login_rejects_wrong_password(self, api_client):
        UserFactory(phone_number='09120000002', password='StrongPassword@123')

        response = api_client.post(
            reverse('accounts:login'),
            {'phone_number': '09120000002', 'password': 'nope'},
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_guest_account_cannot_login_with_a_password(self, api_client):
        user = User.objects.create_user(phone_number='09120000003', password=None)
        assert user.has_usable_password() is False

        response = api_client.post(
            reverse('accounts:login'),
            {'phone_number': '09120000003', 'password': 'anything'},
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert 'detail' in response.data

    def test_unauthenticated_profile_is_rejected(self, api_client):
        response = api_client.get(reverse('accounts:profile'))
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )


@pytest.mark.django_db
class TestSetPassword:
    def test_guest_can_set_password_and_then_login(self, api_client):
        user = User.objects.create_user(phone_number='09120000004', password=None)
        api_client.force_authenticate(user=user)

        response = api_client.post(
            reverse('accounts:set-password'),
            {
                'password': 'StrongPassword@123',
                'password_confirm': 'StrongPassword@123',
            },
        )

        assert response.status_code == status.HTTP_200_OK
        user.refresh_from_db()
        assert user.has_usable_password() is True

        api_client.force_authenticate(user=None)
        login = api_client.post(
            reverse('accounts:login'),
            {'phone_number': '09120000004', 'password': 'StrongPassword@123'},
        )
        assert login.status_code == status.HTTP_200_OK
        assert 'access' in login.data

    def test_registered_user_cannot_replace_password_via_set_password(self, api_client):
        user = UserFactory(password='StrongPassword@123')
        api_client.force_authenticate(user=user)

        response = api_client.post(
            reverse('accounts:set-password'),
            {
                'password': 'NewStrongPass@123',
                'password_confirm': 'NewStrongPass@123',
            },
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        user.refresh_from_db()
        assert user.check_password('StrongPassword@123')
