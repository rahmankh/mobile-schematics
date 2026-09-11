"""
CORS contract for browser/mobile-web clients talking to /api/v1/.

Native apps ignore CORS; Expo web, Vite, and the technician dashboard on
another origin need Access-Control-Allow-Origin plus Authorization in preflight.
"""

from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework import status


ALLOWED_DEV_ORIGIN = 'http://localhost:5173'


@pytest.mark.django_db
def test_get_from_allowed_origin_echoes_access_control_allow_origin(api_client):
    response = api_client.get(
        reverse('schematics:brand-list'),
        HTTP_ORIGIN=ALLOWED_DEV_ORIGIN,
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.get('Access-Control-Allow-Origin') == ALLOWED_DEV_ORIGIN


@pytest.mark.django_db
def test_preflight_allows_authorization_header(api_client):
    response = api_client.options(
        reverse('schematics:brand-list'),
        HTTP_ORIGIN=ALLOWED_DEV_ORIGIN,
        HTTP_ACCESS_CONTROL_REQUEST_METHOD='GET',
        HTTP_ACCESS_CONTROL_REQUEST_HEADERS='authorization',
    )

    assert response.status_code in (status.HTTP_200_OK, status.HTTP_204_NO_CONTENT)
    assert response.get('Access-Control-Allow-Origin') == ALLOWED_DEV_ORIGIN
    allow_headers = response.get('Access-Control-Allow-Headers', '').lower()
    assert 'authorization' in allow_headers


@pytest.mark.django_db
def test_unknown_origin_is_not_reflected(api_client, settings):
    settings.CORS_ALLOW_ALL_ORIGINS = False
    settings.CORS_ALLOWED_ORIGINS = [ALLOWED_DEV_ORIGIN]

    response = api_client.get(
        reverse('schematics:brand-list'),
        HTTP_ORIGIN='https://evil.example',
    )

    assert response.get('Access-Control-Allow-Origin') != 'https://evil.example'


def test_env_example_documents_cors_origins():
    from pathlib import Path
    from django.conf import settings as django_settings

    example = (Path(django_settings.BASE_DIR) / '.env.example').read_text(encoding='utf-8')
    assert 'CORS_ALLOWED_ORIGINS' in example
