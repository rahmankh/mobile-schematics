"""
Account helpers shared by registration, guest checkout, and password claiming.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction

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
