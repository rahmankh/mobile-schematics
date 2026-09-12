"""
Phone OTP password reset.

Request always looks like a send. Confirm verifies a hashed, time-limited code
and sets a new password. Guests and unknown/inactive numbers get no OTP so this
cannot mint a login on a checkout-only row.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets

from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from accounts.models import PasswordResetChallenge
from accounts.phone import normalize_iranian_phone

logger = logging.getLogger(__name__)
User = get_user_model()

_OTP_PREFIX = 'password-reset-otp-v1:'

GENERIC_REQUEST_MESSAGE = (
    'اگر این شماره حساب داشته باشد، کد بازیابی ارسال شد.'
)
GENERIC_CONFIRM_ERROR = 'کد بازیابی نامعتبر یا منقضی است.'
CONFIRM_SUCCESS_MESSAGE = 'رمز عبور با موفقیت تغییر کرد. اکنون وارد شوید.'


class InvalidResetError(Exception):
    """Wrong, expired, locked, or missing OTP. Safe to show GENERIC_CONFIRM_ERROR."""


def hash_otp(otp: str) -> str:
    """SHA-256 HMAC keyed by SECRET_KEY. Stored on PasswordResetChallenge."""
    key = str(settings.SECRET_KEY).encode('utf-8')
    message = f'{_OTP_PREFIX}{otp}'.encode('utf-8')
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def generate_otp() -> str:
    length = int(getattr(settings, 'PASSWORD_RESET_OTP_LENGTH', 6))
    return f'{secrets.randbelow(10 ** length):0{length}d}'


def deliver_reset_otp(phone_number: str, otp: str) -> None:
    """
    Hand the code to the current delivery backend.

    Production should swap this for SMS. DEBUG logs the code for local catalog
    testing; the HTTP response never includes it.
    """
    logger.info('Password reset OTP issued for %s', phone_number)
    if settings.DEBUG:
        logger.debug('DEV password-reset OTP for %s: %s', phone_number, otp)


def _eligible_user(phone_number: str):
    try:
        user = User.objects.get(phone_number=phone_number)
    except User.DoesNotExist:
        return None
    if not user.is_active or not user.has_usable_password():
        return None
    return user


def request_password_reset(phone_number: str) -> None:
    """
    Issue a new OTP when the phone belongs to an active password-login account.

    Unknown, inactive, and guest numbers are silent no-ops. A recent unused
    challenge is left in place so rotating IPs cannot SMS-bomb one number.
    """
    try:
        phone_number = normalize_iranian_phone(phone_number)
    except DRFValidationError:
        return

    user = _eligible_user(phone_number)
    if user is None:
        return

    now = timezone.now()
    resend_seconds = int(getattr(settings, 'PASSWORD_RESET_OTP_RESEND_SECONDS', 60))
    if PasswordResetChallenge.objects.filter(
        phone_number=phone_number,
        used_at__isnull=True,
        created_at__gte=now - timedelta(seconds=resend_seconds),
    ).exists():
        return

    PasswordResetChallenge.objects.filter(
        user=user,
        used_at__isnull=True,
    ).update(used_at=now)

    otp = generate_otp()
    ttl = int(getattr(settings, 'PASSWORD_RESET_OTP_TTL_SECONDS', 600))
    PasswordResetChallenge.objects.create(
        user=user,
        phone_number=phone_number,
        otp_hash=hash_otp(otp),
        expires_at=now + timedelta(seconds=ttl),
    )
    deliver_reset_otp(phone_number, otp)


def confirm_password_reset(phone_number: str, otp: str, new_password: str):
    """
    Verify the latest open OTP and replace the password.

    On success, outstanding refresh tokens are blacklisted and Django sessions
    for that user are dropped. Access JWTs die because SIMPLE_JWT checks the
    password hash claim. Does not start a new session or mint JWT.
    """
    try:
        phone_number = normalize_iranian_phone(phone_number)
    except DRFValidationError as exc:
        raise InvalidResetError() from exc

    otp = str(otp or '').strip()
    now = timezone.now()
    max_attempts = int(getattr(settings, 'PASSWORD_RESET_OTP_MAX_ATTEMPTS', 5))
    user = None

    with transaction.atomic():
        challenge = (
            PasswordResetChallenge.objects.select_for_update()
            .select_related('user')
            .filter(
                phone_number=phone_number,
                used_at__isnull=True,
                expires_at__gt=now,
            )
            .order_by('-created_at')
            .first()
        )
        if challenge is None:
            accepted = False
        else:
            account = challenge.user
            if not account.is_active or not account.has_usable_password():
                challenge.used_at = now
                challenge.save(update_fields=['used_at'])
                accepted = False
            elif challenge.attempt_count >= max_attempts:
                challenge.used_at = now
                challenge.save(update_fields=['used_at'])
                accepted = False
            elif not hmac.compare_digest(challenge.otp_hash, hash_otp(otp)):
                challenge.attempt_count += 1
                update_fields = ['attempt_count']
                if challenge.attempt_count >= max_attempts:
                    challenge.used_at = now
                    update_fields.append('used_at')
                challenge.save(update_fields=update_fields)
                accepted = False
            else:
                account.set_password(new_password)
                account.save(update_fields=['password'])
                challenge.used_at = now
                challenge.attempt_count += 1
                challenge.save(update_fields=['used_at', 'attempt_count'])
                PasswordResetChallenge.objects.filter(
                    user=account,
                    used_at__isnull=True,
                ).update(used_at=now)
                user = account
                accepted = True

    if not accepted or user is None:
        raise InvalidResetError()

    revoke_auth_after_password_change(user)
    return user


def revoke_auth_after_password_change(user) -> None:
    """Drop refresh JWTs and browser sessions issued before the password change."""
    for token in OutstandingToken.objects.filter(user=user):
        BlacklistedToken.objects.get_or_create(token=token)

    user_id = str(user.pk)
    for session in Session.objects.filter(expire_date__gte=timezone.now()):
        data = session.get_decoded()
        if str(data.get('_auth_user_id')) == user_id:
            session.delete()
