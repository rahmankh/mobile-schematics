"""
Pagination contract for catalog list endpoints.

Clients must receive a page envelope (`count`, `next`, `previous`, `results`)
so mobile lists can load brands/models/schematics incrementally.
"""

from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework import status

from schematics.factories import BrandFactory, PhoneModelFactory, SchematicFactory


def _assert_page_envelope(payload: dict) -> None:
    assert isinstance(payload, dict)
    for key in ('count', 'next', 'previous', 'results'):
        assert key in payload
    assert isinstance(payload['results'], list)
    assert isinstance(payload['count'], int)


@pytest.mark.django_db
class TestCatalogPagination:
    def test_brand_list_uses_page_envelope_and_page_size(self, api_client):
        BrandFactory.create_batch(5)

        response = api_client.get(reverse('schematics:brand-list'), {'page_size': 2})

        assert response.status_code == status.HTTP_200_OK
        _assert_page_envelope(response.data)
        assert response.data['count'] >= 5
        assert len(response.data['results']) == 2
        assert response.data['next'] is not None
        assert response.data['previous'] is None

    def test_brand_list_second_page_has_previous_link(self, api_client):
        BrandFactory.create_batch(5)

        first = api_client.get(reverse('schematics:brand-list'), {'page_size': 2})
        second = api_client.get(reverse('schematics:brand-list'), {'page': 2, 'page_size': 2})

        assert second.status_code == status.HTTP_200_OK
        assert second.data['previous'] is not None
        first_ids = {row['id'] for row in first.data['results']}
        second_ids = {row['id'] for row in second.data['results']}
        assert first_ids.isdisjoint(second_ids)

    def test_phone_model_list_is_paginated(self, api_client):
        PhoneModelFactory.create_batch(4)

        response = api_client.get(reverse('schematics:phone-model-list'), {'page_size': 3})

        assert response.status_code == status.HTTP_200_OK
        _assert_page_envelope(response.data)
        assert len(response.data['results']) == 3
        assert response.data['count'] >= 4

    def test_schematic_list_is_paginated(self, api_client):
        SchematicFactory.create_batch(4)

        response = api_client.get(reverse('schematics:schematic-list'), {'page_size': 2})

        assert response.status_code == status.HTTP_200_OK
        _assert_page_envelope(response.data)
        assert len(response.data['results']) == 2
        assert response.data['count'] >= 4

    def test_page_size_is_capped(self, api_client):
        BrandFactory.create_batch(3)

        response = api_client.get(reverse('schematics:brand-list'), {'page_size': 10_000})

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) <= 100
