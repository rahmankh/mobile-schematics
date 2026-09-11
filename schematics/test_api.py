"""
API tests for schematic list/detail and the download URL contract.

The original bug: SchematicFileListSerializer reversed `schematics:file-download`
while urls.py registered `schematics:schematic-file-download`, which 500'd detail.
"""

from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework import status

from schematics.factories import (
    BrandFactory,
    PhoneModelFactory,
    SchematicCategoryFactory,
    SchematicFactory,
    SchematicFileFactory,
)


@pytest.mark.django_db
class TestSchematicDetailAPI:
    """Cover the public detail endpoint, view counter, and download URL name."""

    def test_detail_returns_200_and_nested_files_with_correct_download_url(self, api_client):
        schematic_file = SchematicFileFactory()
        schematic = schematic_file.schematic
        url = reverse('schematics:schematic-detail', kwargs={'pk': schematic.pk})

        response = api_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data['id'] == schematic.pk
        assert response.data['title'] == schematic.title
        assert len(response.data['files']) == 1

        file_payload = response.data['files'][0]
        expected_path = reverse(
            'schematics:schematic-file-download',
            kwargs={'pk': schematic_file.pk},
        )
        assert file_payload['download_url'].endswith(expected_path)
        # Paid binaries must not be advertised as a public /media/ URL.
        assert '/media/' not in file_payload['download_url']
        assert 'file' not in file_payload

    def test_detail_increments_view_count_atomically(self, api_client):
        schematic = SchematicFactory(view_count=4)
        url = reverse('schematics:schematic-detail', kwargs={'pk': schematic.pk})

        first = api_client.get(url)
        second = api_client.get(url)

        assert first.data['view_count'] == 5
        assert second.data['view_count'] == 6

    def test_detail_unknown_id_returns_404(self, api_client):
        url = reverse('schematics:schematic-detail', kwargs={'pk': 999_999})
        response = api_client.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_anonymous_users_can_read_detail(self, api_client):
        schematic = SchematicFactory()
        url = reverse('schematics:schematic-detail', kwargs={'pk': schematic.pk})
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK

    def test_list_endpoint_includes_annotated_files_count(self, api_client):
        schematic = SchematicFactory()
        SchematicFileFactory(schematic=schematic)
        SchematicFileFactory(schematic=schematic, file_title='Page 2')

        response = api_client.get(reverse('schematics:schematic-list'))

        assert response.status_code == status.HTTP_200_OK
        row = next(item for item in response.data['results'] if item['id'] == schematic.pk)
        assert row['files_count'] == 2

    def test_list_can_filter_by_category_slug_and_model_id(self, api_client):
        brand = BrandFactory(name='Samsung', slug='samsung')
        model = PhoneModelFactory(brand=brand, name='S24 Ultra', slug='s24-ultra')
        category = SchematicCategoryFactory(title='Boardview', slug='boardview')
        matching = SchematicFactory(phone_model=model, category=category, title='Main Board')
        SchematicFactory(title='Other Doc')

        response = api_client.get(
            reverse('schematics:schematic-list'),
            {'category': 'boardview', 'model_id': model.pk},
        )

        ids = [row['id'] for row in response.data['results']]
        assert matching.pk in ids
        assert len(ids) == 1

    def test_brand_list_annotates_models_count(self, api_client):
        brand = BrandFactory(name='Xiaomi', slug='xiaomi')
        PhoneModelFactory(brand=brand, name='Redmi Note 13', slug='redmi-note-13')
        PhoneModelFactory(brand=brand, name='14 Ultra', slug='14-ultra')

        response = api_client.get(reverse('schematics:brand-list'))

        row = next(item for item in response.data['results'] if item['slug'] == 'xiaomi')
        assert row['models_count'] == 2

    def test_phone_model_list_filters_by_brand_slug(self, api_client):
        samsung = BrandFactory(name='Samsung', slug='samsung')
        xiaomi = BrandFactory(name='Xiaomi', slug='xiaomi')
        PhoneModelFactory(brand=samsung, name='A55', slug='a55')
        PhoneModelFactory(brand=xiaomi, name='Poco F6', slug='poco-f6')

        response = api_client.get(reverse('schematics:phone-model-list'), {'brand': 'samsung'})

        names = [row['name'] for row in response.data['results']]
        assert names == ['A55']
