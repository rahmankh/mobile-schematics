"""
Rate limits on brute-force and bandwidth-sensitive API routes.

DRF ScopedRateThrottle (and subclasses) is used instead of django-ratelimit so
clients get a JSON 429 with Retry-After. Cache-backed counters need LocMem in
tests and Redis (CACHE_URL) in production.
"""

from __future__ import annotations

import pytest
from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIRequestFactory
from rest_framework.throttling import SimpleRateThrottle

from config.throttling import DownloadRateThrottle, LoginRateThrottle, OtpRateThrottle
from schematics.factories import SchematicFileFactory, UserFactory


@pytest.fixture
def tight_throttles(settings):
    """Drop every sensitive scope to 2/min so tests do not wait a real minute."""
    cache.clear()
    rates = {
        'login': '2/min',
        'otp': '2/min',
        'downloads': '2/min',
    }
    settings.REST_FRAMEWORK = {
        **settings.REST_FRAMEWORK,
        'DEFAULT_THROTTLE_RATES': rates,
    }
    # DRF copies DEFAULT_THROTTLE_RATES onto the class at import time.
    original = SimpleRateThrottle.THROTTLE_RATES
    SimpleRateThrottle.THROTTLE_RATES = rates
    yield
    SimpleRateThrottle.THROTTLE_RATES = original
    cache.clear()


@pytest.mark.django_db
def test_login_returns_429_after_burst(api_client, tight_throttles):
    url = reverse('accounts:login')
    payload = {'phone_number': '09120000000', 'password': 'wrong-password'}

    assert api_client.post(url, payload).status_code != status.HTTP_429_TOO_MANY_REQUESTS
    assert api_client.post(url, payload).status_code != status.HTTP_429_TOO_MANY_REQUESTS
    blocked = api_client.post(url, payload)

    assert blocked.status_code == status.HTTP_429_TOO_MANY_REQUESTS


@pytest.mark.django_db
def test_register_shares_the_login_throttle(api_client, tight_throttles):
    url = reverse('accounts:register')
    payload = {
        'phone_number': '09121111111',
        'first_name': 'A',
        'last_name': 'B',
        'repair_shop_name': 'Shop',
        'password': 'StrongPassword@123',
        'password_confirm': 'StrongPassword@123',
    }

    api_client.post(url, payload)
    payload['phone_number'] = '09121111112'
    api_client.post(url, payload)
    payload['phone_number'] = '09121111113'
    blocked = api_client.post(url, payload)

    assert blocked.status_code == status.HTTP_429_TOO_MANY_REQUESTS


@pytest.mark.django_db
def test_download_returns_429_after_burst(api_client, tight_throttles):
    user = UserFactory()
    schematic_file = SchematicFileFactory()
    api_client.force_authenticate(user=user)
    url = reverse('schematics:schematic-file-download', kwargs={'pk': schematic_file.pk})

    api_client.get(url)
    api_client.get(url)
    blocked = api_client.get(url)

    assert blocked.status_code == status.HTTP_429_TOO_MANY_REQUESTS


def test_otp_throttle_blocks_a_third_anonymous_call(tight_throttles):
    """
    SMS OTP is not shipped yet; the throttle class must still be wired so the
    future view can set `throttle_classes = [OtpRateThrottle]`.
    """
    factory = APIRequestFactory()
    request = factory.post('/api/v1/accounts/otp/')
    request.user = AnonymousUser()
    view = type('OtpStubView', (), {})()
    throttle = OtpRateThrottle()

    assert throttle.allow_request(request, view) is True
    assert throttle.allow_request(request, view) is True
    assert throttle.allow_request(request, view) is False


def test_throttle_rates_are_configured():
    from django.conf import settings as django_settings

    rates = django_settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']
    assert 'login' in rates
    assert 'otp' in rates
    assert 'downloads' in rates
