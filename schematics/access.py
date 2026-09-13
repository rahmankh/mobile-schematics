"""
Human-readable download denials for anonymous and unentitled callers.

The download view stays AllowAny so guests see Persian copy (and a guest-checkout
hint) instead of DRF's English "credentials were not provided".
"""

from __future__ import annotations

from rest_framework import status


def denied_download_payload(user, schematic) -> tuple[dict, int]:
    """
    Return (body, http_status) when `user_can_download` is False.

    `code` is a stable machine key for the mobile client; `detail` is Persian UX.
    """
    authenticated = bool(user is not None and getattr(user, 'is_authenticated', False))
    can_purchase = (not schematic.is_free) and schematic.price > 0

    if not authenticated:
        return {
            'detail': (
                'برای مشاهده این فایل باید وارد حساب شوید '
                'یا خرید مهمان با شماره موبایل انجام دهید.'
            ),
            'code': 'login_required',
            'guest_checkout_allowed': can_purchase,
            'can_purchase': can_purchase,
        }, status.HTTP_401_UNAUTHORIZED

    return {
        'detail': (
            'برای مشاهده این فایل باید نقشه را به صورت تکی خریداری کنید '
            'یا از موجودی کیف پول پرداخت نمایید.'
        ),
        'code': 'purchase_required',
        'guest_checkout_allowed': can_purchase,
        'can_purchase': can_purchase,
    }, status.HTTP_403_FORBIDDEN
