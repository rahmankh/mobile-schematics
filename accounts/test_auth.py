"""
Auth API: Iranian phone register/login, guest accounts cannot password-login,
and authenticated guests can set a password to claim the account.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import identify_hasher
from django.urls import reverse
from rest_framework import status
from rest_framework_simplejwt.tokens import AccessToken

from schematics.factories import UserFactory

User = get_user_model()

REGISTER_PAYLOAD = {
    'phone_number': '09123000901',
    'first_name': 'Sara',
    'last_name': 'Karimi',
    'repair_shop_name': 'Shiraz Repair',
    'password': 'StrongPassword@123',
    'password_confirm': 'StrongPassword@123',
}


@pytest.mark.django_db
class TestTechnicianAuthFlow:
    """End-to-end register → hashed password → JWT → profile for a non-admin technician."""

    def test_register_hashes_password_issues_jwt_and_opens_profile(self, api_client):
        response = api_client.post(reverse('accounts:register'), REGISTER_PAYLOAD)

        assert response.status_code == status.HTTP_201_CREATED
        assert 'password' not in response.data
        assert 'password' not in response.data.get('user', {})
        assert response.data['user']['phone_number'] == '09123000901'
        assert response.data['user']['is_guest'] is False
        assert 'access' in response.data
        assert 'refresh' in response.data

        user = User.objects.get(phone_number='09123000901')
        assert user.check_password('StrongPassword@123')
        assert user.password != 'StrongPassword@123'
        identify_hasher(user.password)
        assert user.role == User.RoleChoices.TECHNICIAN
        assert user.is_staff is False
        assert user.is_superuser is False
        assert user.is_active is True

        token = AccessToken(response.data['access'])
        assert int(token['user_id']) == user.pk

        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {response.data["access"]}')
        profile = api_client.get(reverse('accounts:profile'))
        assert profile.status_code == status.HTTP_200_OK
        assert profile.data['phone_number'] == '09123000901'
        assert profile.data['repair_shop_name'] == 'Shiraz Repair'
        assert profile.data['is_guest'] is False

    def test_register_ignores_privilege_fields(self, api_client):
        payload = {
            **REGISTER_PAYLOAD,
            'phone_number': '09123000902',
            'role': User.RoleChoices.ADMIN,
            'is_staff': True,
            'is_superuser': True,
            'is_active': False,
        }
        response = api_client.post(reverse('accounts:register'), payload)

        assert response.status_code == status.HTTP_201_CREATED
        user = User.objects.get(phone_number='09123000902')
        assert user.role == User.RoleChoices.TECHNICIAN
        assert user.is_staff is False
        assert user.is_superuser is False
        assert user.is_active is True

    def test_register_rejects_weak_password(self, api_client):
        payload = {
            **REGISTER_PAYLOAD,
            'phone_number': '09123000903',
            'password': 'password',
            'password_confirm': 'password',
        }
        response = api_client.post(reverse('accounts:register'), payload)
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert User.objects.filter(phone_number='09123000903').exists() is False

    def test_login_issues_jwt_that_authenticates_profile(self, api_client):
        UserFactory(
            phone_number='09123000904',
            password='StrongPassword@123',
            first_name='Ali',
            repair_shop_name='Tehran Shop',
        )
        response = api_client.post(
            reverse('accounts:login'),
            {'phone_number': '09123000904', 'password': 'StrongPassword@123'},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data['user']['phone_number'] == '09123000904'
        assert response.data['user']['is_guest'] is False
        token = AccessToken(response.data['access'])
        user = User.objects.get(phone_number='09123000904')
        assert int(token['user_id']) == user.pk

        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {response.data["access"]}')
        profile = api_client.get(reverse('accounts:profile'))
        assert profile.status_code == status.HTTP_200_OK
        assert profile.data['repair_shop_name'] == 'Tehran Shop'

        refresh = api_client.post(
            reverse('accounts:token_refresh'),
            {'refresh': response.data['refresh']},
        )
        assert refresh.status_code == status.HTTP_200_OK
        assert refresh.data['access']
        assert refresh.data['refresh']
        assert refresh.data['refresh'] != response.data['refresh']
        AccessToken(refresh.data['access'])

    def test_inactive_technician_cannot_login(self, api_client):
        user = UserFactory(phone_number='09123000905', password='StrongPassword@123')
        user.is_active = False
        user.save(update_fields=['is_active'])
        response = api_client.post(
            reverse('accounts:login'),
            {'phone_number': '09123000905', 'password': 'StrongPassword@123'},
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


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


@pytest.mark.django_db
class TestJWTRotationAndBlacklist:
    def test_settings_enable_rotation_and_blacklist(self):
        from datetime import timedelta

        from django.conf import settings as django_settings

        assert django_settings.SIMPLE_JWT['ROTATE_REFRESH_TOKENS'] is True
        assert django_settings.SIMPLE_JWT['BLACKLIST_AFTER_ROTATION'] is True
        assert django_settings.SIMPLE_JWT['CHECK_REVOKE_TOKEN'] is True
        assert django_settings.SIMPLE_JWT['ACCESS_TOKEN_LIFETIME'] == timedelta(minutes=60)
        assert django_settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME'] == timedelta(days=7)
        assert 'rest_framework_simplejwt.token_blacklist' in django_settings.INSTALLED_APPS

    def test_refresh_rotates_and_blacklists_previous_token(self, api_client):
        UserFactory(phone_number='09123000920', password='StrongPassword@123')
        login = api_client.post(
            reverse('accounts:login'),
            {'phone_number': '09123000920', 'password': 'StrongPassword@123'},
        )
        old_refresh = login.data['refresh']

        rotated = api_client.post(
            reverse('accounts:token_refresh'),
            {'refresh': old_refresh},
            format='json',
        )
        assert rotated.status_code == status.HTTP_200_OK
        assert rotated.data['refresh'] != old_refresh

        reused = api_client.post(
            reverse('accounts:token_refresh'),
            {'refresh': old_refresh},
            format='json',
        )
        assert reused.status_code == status.HTTP_401_UNAUTHORIZED

        follow_up = api_client.post(
            reverse('accounts:token_refresh'),
            {'refresh': rotated.data['refresh']},
            format='json',
        )
        assert follow_up.status_code == status.HTTP_200_OK
        assert follow_up.data['access']

    def test_logout_blacklists_refresh_token(self, api_client):
        user = UserFactory(phone_number='09123000921', password='StrongPassword@123')
        login = api_client.post(
            reverse('accounts:login'),
            {'phone_number': '09123000921', 'password': 'StrongPassword@123'},
        )
        assert login.status_code == status.HTTP_200_OK
        user.refresh_from_db()
        assert user.last_login is not None

        logout = api_client.post(
            reverse('accounts:logout'),
            {'refresh': login.data['refresh']},
            format='json',
        )
        assert logout.status_code == status.HTTP_200_OK

        refresh = api_client.post(
            reverse('accounts:token_refresh'),
            {'refresh': login.data['refresh']},
            format='json',
        )
        assert refresh.status_code == status.HTTP_401_UNAUTHORIZED

        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {login.data["access"]}')
        profile = api_client.get(reverse('accounts:profile'))
        assert profile.status_code == status.HTTP_200_OK

    def test_logout_without_refresh_is_rejected(self, api_client):
        response = api_client.post(reverse('accounts:logout'), {}, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST
