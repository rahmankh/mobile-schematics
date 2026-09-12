"""
OpenAPI / Swagger contract for the mobile and frontend teams.

`/api/schema/` is the machine-readable OpenAPI 3 document.
`/api/docs/` is Swagger UI so humans can try endpoints without Postman.
"""

from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework import status


@pytest.mark.django_db
def test_openapi_schema_is_version_3_and_lists_core_paths(api_client):
    response = api_client.get(reverse('schema'), HTTP_ACCEPT='application/json')

    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert payload['openapi'].startswith('3.')
    assert 'Mobile Schematics' in payload['info']['title']

    paths = payload['paths']
    assert '/api/v1/accounts/login/' in paths
    assert '/api/v1/schematics/brands/' in paths
    assert '/api/v1/schematics/' in paths
    assert '/api/v1/schematics/files/{id}/download/' in paths or any(
        'download' in path for path in paths
    )
    assert any(path.endswith('/payments/request/') for path in paths)
    assert any(path.endswith('/payments/claim/') for path in paths)


@pytest.mark.django_db
def test_swagger_ui_is_served_at_api_docs(api_client):
    response = api_client.get(reverse('swagger-ui'))

    assert response.status_code == status.HTTP_200_OK
    html = response.content.decode('utf-8').lower()
    assert 'swagger' in html


def test_schema_url_is_api_docs_sibling():
    assert reverse('swagger-ui') == '/api/docs/'
    assert reverse('schema') == '/api/schema/'
