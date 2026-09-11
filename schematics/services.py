"""
Commerce helpers for single-copy schematic sales.

HTTP views must call `assert_schematic_purchasable` during checkout and
`fulfill_schematic_purchase` only after a payment gateway verify() success.
"""

from __future__ import annotations

from decimal import Decimal

from .models import Schematic, SchematicPurchase


class SchematicNotPurchasable(Exception):
    """Raised when the schematic is free, unpriced, or otherwise not sold à la carte."""


class AlreadyPurchased(Exception):
    """Raised when the user already has a SchematicPurchase row for this document."""


def assert_schematic_purchasable(user, schematic: Schematic) -> None:
    """
    Validate that `user` may start a checkout for `schematic`.

    Does not write any rows. Free documents are downloaded via the access matrix,
    not purchased. Duplicate ownership is a conflict, not a new charge.
    """
    if schematic.is_free or schematic.price <= 0:
        raise SchematicNotPurchasable('این شماتیک برای خرید تکی در دسترس نیست.')
    if SchematicPurchase.objects.filter(user=user, schematic=schematic).exists():
        raise AlreadyPurchased('این شماتیک را قبلاً خریداری کرده‌اید.')


def fulfill_schematic_purchase(
    user,
    schematic: Schematic,
    price_paid: Decimal | int | None = None,
) -> tuple[SchematicPurchase, bool]:
    """
    Insert the entitlement ledger row after payment has been verified.

    Returns (purchase, created). A second call is idempotent so a repeated
    gateway callback cannot create a duplicate unique-constraint error.
    """
    amount = schematic.price if price_paid is None else price_paid
    purchase, created = SchematicPurchase.objects.get_or_create(
        user=user,
        schematic=schematic,
        defaults={'price_paid': amount},
    )
    return purchase, created
