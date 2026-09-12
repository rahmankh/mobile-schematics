"""
Phone OTP password reset: hashed at rest, enumeration-safe request, confirm
sets a new password and revokes prior JWTs. Guests cannot reset into a takeover.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework_simplejwt.tokens import AccessToken

from accounts.models import PasswordResetChallenge
from accounts.password_reset import (
    CONFIRM_SUCCESS_MESSAGE,
    GENERIC_CONFIRM_ERROR,
    GENERIC_REQUEST_MESSAGE,
    hash_otp,
)
from schematics.factories import UserFactory

User = get_user_model()

RESET_PHONE = '09123000701'
NEW_PASSWORD = 'BrandNewPass@456'


@pytest.fixture
def reset_otp(monkeypatch):
    monkeypatch.setattr('accounts.password_reset.generate_otp', lambda: '847291')
    return '847291'


def _confirm_payload(otp: str, phone: str = RESET_PHONE, **overrides) -> dict:
    payload = {
        'phone_number': phone,
        'otp': otp,
        'password': NEW_PASSWORD,
        'password_confirm': NEW_PASSWORD,
    }
    payload.update(overrides)
    return payload


@pytest.mark.django_db
class TestPasswordResetRequest:
    def test_unknown_phone_returns_generic_success_without_challenge(self, api_client):
        response = api_client.post(
            reverse('accounts:password-reset'),
            {'phone_number': '09123000799'},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data['detail'] == GENERIC_REQUEST_MESSAGE
        assert 'otp' not in response.data
        assert PasswordResetChallenge.objects.count() == 0

    def test_guest_cannot_receive_a_reset_otp(self, api_client):
        User.objects.create_user(phone_number=RESET_PHONE, password=None)
        response = api_client.post(
            reverse('accounts:password-reset'),
            {'phone_number': RESET_PHONE},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data['detail'] == GENERIC_REQUEST_MESSAGE
        assert PasswordResetChallenge.objects.count() == 0

    def test_inactive_user_cannot_receive_a_reset_otp(self, api_client, reset_otp):
        user = UserFactory(phone_number=RESET_PHONE, password='StrongPassword@123')
        user.is_active = False
        user.save(update_fields=['is_active'])
        response = api_client.post(
            reverse('accounts:password-reset'),
            {'phone_number': RESET_PHONE},
        )
        assert response.status_code == status.HTTP_200_OK
        assert PasswordResetChallenge.objects.count() == 0

    def test_registered_user_stores_hashed_otp_not_plaintext(
        self, api_client, reset_otp
    ):
        UserFactory(phone_number=RESET_PHONE, password='StrongPassword@123')
        response = api_client.post(
            reverse('accounts:password-reset'),
            {'phone_number': '+989123000701'},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data['detail'] == GENERIC_REQUEST_MESSAGE
        assert '847291' not in str(response.data)
        challenge = PasswordResetChallenge.objects.get(phone_number=RESET_PHONE)
        assert challenge.otp_hash == hash_otp(reset_otp)
        assert challenge.otp_hash != reset_otp
        assert challenge.used_at is None

    def test_invalid_phone_is_rejected(self, api_client):
        response = api_client.post(
            reverse('accounts:password-reset'),
            {'phone_number': 'not-a-phone'},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert PasswordResetChallenge.objects.count() == 0

    def test_resend_cooldown_keeps_the_first_otp(self, api_client, monkeypatch):
        UserFactory(phone_number=RESET_PHONE, password='StrongPassword@123')
        codes = iter(['111111', '222222'])
        monkeypatch.setattr(
            'accounts.password_reset.generate_otp',
            lambda: next(codes),
        )
        api_client.post(reverse('accounts:password-reset'), {'phone_number': RESET_PHONE})
        api_client.post(reverse('accounts:password-reset'), {'phone_number': RESET_PHONE})
        assert PasswordResetChallenge.objects.filter(used_at__isnull=True).count() == 1
        challenge = PasswordResetChallenge.objects.get(used_at__isnull=True)
        assert challenge.otp_hash == hash_otp('111111')

    def test_new_otp_after_cooldown_invalidates_the_previous_one(
        self, api_client, monkeypatch
    ):
        UserFactory(phone_number=RESET_PHONE, password='StrongPassword@123')
        codes = iter(['111111', '222222'])
        monkeypatch.setattr(
            'accounts.password_reset.generate_otp',
            lambda: next(codes),
        )
        api_client.post(reverse('accounts:password-reset'), {'phone_number': RESET_PHONE})
        PasswordResetChallenge.objects.update(
            created_at=timezone.now() - timedelta(seconds=61),
        )
        api_client.post(reverse('accounts:password-reset'), {'phone_number': RESET_PHONE})
        open_challenges = PasswordResetChallenge.objects.filter(used_at__isnull=True)
        assert open_challenges.count() == 1
        assert open_challenges.get().otp_hash == hash_otp('222222')
        confirm = api_client.post(
            reverse('accounts:password-reset-confirm'),
            _confirm_payload('111111'),
        )
        assert confirm.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestPasswordResetConfirm:
    def test_valid_otp_sets_password_and_does_not_issue_jwt(
        self, api_client, reset_otp
    ):
        UserFactory(phone_number=RESET_PHONE, password='StrongPassword@123')
        api_client.post(reverse('accounts:password-reset'), {'phone_number': RESET_PHONE})

        response = api_client.post(
            reverse('accounts:password-reset-confirm'),
            _confirm_payload(reset_otp),
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data['detail'] == CONFIRM_SUCCESS_MESSAGE
        assert 'access' not in response.data
        assert 'refresh' not in response.data
        assert 'otp' not in response.data

        user = User.objects.get(phone_number=RESET_PHONE)
        assert user.check_password(NEW_PASSWORD)
        assert user.check_password('StrongPassword@123') is False
        assert user.role == User.RoleChoices.TECHNICIAN
        assert user.is_staff is False

        old_login = api_client.post(
            reverse('accounts:login'),
            {'phone_number': RESET_PHONE, 'password': 'StrongPassword@123'},
        )
        assert old_login.status_code == status.HTTP_401_UNAUTHORIZED
        new_login = api_client.post(
            reverse('accounts:login'),
            {'phone_number': RESET_PHONE, 'password': NEW_PASSWORD},
        )
        assert new_login.status_code == status.HTTP_200_OK
        assert 'access' in new_login.data

    def test_reset_revokes_existing_jwts(self, api_client, reset_otp):
        UserFactory(phone_number=RESET_PHONE, password='StrongPassword@123')
        login = api_client.post(
            reverse('accounts:login'),
            {'phone_number': RESET_PHONE, 'password': 'StrongPassword@123'},
        )
        access = login.data['access']
        refresh = login.data['refresh']
        AccessToken(access)

        api_client.post(reverse('accounts:password-reset'), {'phone_number': RESET_PHONE})
        api_client.post(
            reverse('accounts:password-reset-confirm'),
            _confirm_payload(reset_otp),
        )

        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')
        profile = api_client.get(reverse('accounts:profile'))
        assert profile.status_code == status.HTTP_401_UNAUTHORIZED

        api_client.credentials()
        rotated = api_client.post(
            reverse('accounts:token_refresh'),
            {'refresh': refresh},
            format='json',
        )
        assert rotated.status_code == status.HTTP_401_UNAUTHORIZED

    def test_wrong_otp_is_generic_failure(self, api_client, reset_otp):
        UserFactory(phone_number=RESET_PHONE, password='StrongPassword@123')
        api_client.post(reverse('accounts:password-reset'), {'phone_number': RESET_PHONE})
        response = api_client.post(
            reverse('accounts:password-reset-confirm'),
            _confirm_payload('000000'),
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data['detail'] == GENERIC_CONFIRM_ERROR
        user = User.objects.get(phone_number=RESET_PHONE)
        assert user.check_password('StrongPassword@123')

    def test_expired_otp_is_rejected(self, api_client, reset_otp):
        UserFactory(phone_number=RESET_PHONE, password='StrongPassword@123')
        api_client.post(reverse('accounts:password-reset'), {'phone_number': RESET_PHONE})
        PasswordResetChallenge.objects.update(
            expires_at=timezone.now() - timedelta(seconds=1),
        )
        response = api_client.post(
            reverse('accounts:password-reset-confirm'),
            _confirm_payload(reset_otp),
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        user = User.objects.get(phone_number=RESET_PHONE)
        assert user.check_password('StrongPassword@123')

    def test_otp_cannot_be_reused(self, api_client, reset_otp):
        UserFactory(phone_number=RESET_PHONE, password='StrongPassword@123')
        api_client.post(reverse('accounts:password-reset'), {'phone_number': RESET_PHONE})
        first = api_client.post(
            reverse('accounts:password-reset-confirm'),
            _confirm_payload(reset_otp),
        )
        assert first.status_code == status.HTTP_200_OK
        second = api_client.post(
            reverse('accounts:password-reset-confirm'),
            _confirm_payload(reset_otp, password='AnotherPass@789', password_confirm='AnotherPass@789'),
        )
        assert second.status_code == status.HTTP_400_BAD_REQUEST
        user = User.objects.get(phone_number=RESET_PHONE)
        assert user.check_password(NEW_PASSWORD)
        assert user.check_password('AnotherPass@789') is False

    def test_too_many_wrong_attempts_lock_the_challenge(self, reset_otp):
        from accounts.password_reset import InvalidResetError, confirm_password_reset, request_password_reset

        UserFactory(phone_number=RESET_PHONE, password='StrongPassword@123')
        request_password_reset(RESET_PHONE)
        for _ in range(5):
            with pytest.raises(InvalidResetError):
                confirm_password_reset(RESET_PHONE, '000000', NEW_PASSWORD)
        with pytest.raises(InvalidResetError):
            confirm_password_reset(RESET_PHONE, reset_otp, NEW_PASSWORD)
        user = User.objects.get(phone_number=RESET_PHONE)
        assert user.check_password('StrongPassword@123')
        assert PasswordResetChallenge.objects.filter(used_at__isnull=True).count() == 0

    def test_weak_password_is_rejected_without_consuming_otp(
        self, api_client, reset_otp
    ):
        UserFactory(phone_number=RESET_PHONE, password='StrongPassword@123')
        api_client.post(reverse('accounts:password-reset'), {'phone_number': RESET_PHONE})
        response = api_client.post(
            reverse('accounts:password-reset-confirm'),
            _confirm_payload(reset_otp, password='password', password_confirm='password'),
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        user = User.objects.get(phone_number=RESET_PHONE)
        assert user.check_password('StrongPassword@123')
        retry = api_client.post(
            reverse('accounts:password-reset-confirm'),
            _confirm_payload(reset_otp),
        )
        assert retry.status_code == status.HTTP_200_OK
        user.refresh_from_db()
        assert user.check_password(NEW_PASSWORD)

    def test_password_mismatch_is_rejected(self, api_client, reset_otp):
        UserFactory(phone_number=RESET_PHONE, password='StrongPassword@123')
        api_client.post(reverse('accounts:password-reset'), {'phone_number': RESET_PHONE})
        response = api_client.post(
            reverse('accounts:password-reset-confirm'),
            _confirm_payload(
                reset_otp,
                password=NEW_PASSWORD,
                password_confirm='DifferentPass@456',
            ),
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        user = User.objects.get(phone_number=RESET_PHONE)
        assert user.check_password('StrongPassword@123')

    def test_unknown_phone_confirm_is_generic_failure(self, api_client):
        response = api_client.post(
            reverse('accounts:password-reset-confirm'),
            _confirm_payload('847291', phone='09123000798'),
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data['detail'] == GENERIC_CONFIRM_ERROR
