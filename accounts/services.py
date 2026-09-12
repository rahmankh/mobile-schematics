"""
Account helpers shared by registration, guest checkout, and password claiming.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()


def get_or_create_checkout_user(phone_number: str):
    """
    Resolve the technician row for a guest checkout.

    Existing accounts (registered or previous guests) are reused so a paid
    schematic lands on the phone the customer typed. New rows get an unusable
    password — they receive JWT after verify, not a guessed credential.
    """
    try:
        return User.objects.get(phone_number=phone_number), False
    except User.DoesNotExist:
        pass
    try:
        with transaction.atomic():
            user = User.objects.create_user(phone_number=phone_number, password=None)
        return user, True
    except IntegrityError:
        return User.objects.get(phone_number=phone_number), False


def public_account_payload(user) -> dict:
    """Safe identity body for register/login. Never includes password, role, or staff flags."""
    return {
        'id': user.id,
        'phone_number': user.phone_number,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'repair_shop_name': getattr(user, 'repair_shop_name', ''),
        'is_guest': user.is_guest,
    }


def issue_jwt_for(user) -> dict[str, str]:
    """Signed access + refresh pair (SimpleJWT HMAC). Used after register and guest claim."""
    refresh = RefreshToken.for_user(user)
    return {'refresh': str(refresh), 'access': str(refresh.access_token)}
