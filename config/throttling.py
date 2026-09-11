"""
DRF throttle classes for brute-force and download abuse.

Rates live in REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']. LocMem is the default
cache; production should set CACHE_URL to Redis so workers share counters.
"""

from __future__ import annotations

from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class LoginRateThrottle(AnonRateThrottle):
    """IP cap for login, register, and token refresh (credential stuffing)."""

    scope = 'login'


class OtpRateThrottle(AnonRateThrottle):
    """
    IP cap for SMS OTP request/verify.

    Attach with `throttle_classes = [OtpRateThrottle]` when the OTP views land.
    The rate is stricter than login because each send costs a third-party SMS.
    """

    scope = 'otp'


class DownloadRateThrottle(UserRateThrottle):
    """Per-user cap for schematic file streaming."""

    scope = 'downloads'


class GuestCheckoutRateThrottle(AnonRateThrottle):
    """IP cap for passwordless schematic checkout (separate from login)."""

    scope = 'guest_checkout'
