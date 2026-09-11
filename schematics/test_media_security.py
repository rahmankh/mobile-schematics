"""Security tests: protected schematic files must not be reachable via MEDIA_URL."""

from __future__ import annotations

from pathlib import Path

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.urls import reverse
from rest_framework import status

from schematics.factories import (
    MINIMAL_PDF_BYTES,
    SchematicFileFactory,
    SchematicPurchaseFactory,
    UserFactory,
    UserSubscriptionFactory,
)
from schematics.storage import protected_storage


@pytest.mark.django_db
class TestProtectedMediaIsolation:
    def test_uploaded_schematic_file_lives_under_protected_media_root(self, settings):
        schematic_file = SchematicFileFactory()
        stored_path = Path(schematic_file.file.path).resolve()
        protected_root = Path(settings.PROTECTED_MEDIA_ROOT).resolve()
        media_root = Path(settings.MEDIA_ROOT).resolve()

        assert stored_path.is_relative_to(protected_root)
        assert not stored_path.is_relative_to(media_root)
        assert 'protected_schematics/' in schematic_file.file.name.replace('\\', '/')

    def test_storage_refuses_to_build_a_public_url(self):
        schematic_file = SchematicFileFactory()
        with pytest.raises(ValueError, match='not publicly addressable'):
            protected_storage.url(schematic_file.file.name)

    def test_direct_media_url_for_protected_prefix_is_always_404(self, api_client, settings):
        settings.DEBUG = True
        settings.SERVE_MEDIA = True
        response = api_client.get('/media/protected_schematics/samsung/s24/board.pdf')
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_path_traversal_into_protected_prefix_is_404(self, api_client, settings):
        settings.SERVE_MEDIA = True
        response = api_client.get('/media/brands/../protected_schematics/secret.pdf')
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_public_brand_logo_is_served_when_serve_media_is_on(self, api_client, settings):
        settings.SERVE_MEDIA = True
        relative = default_storage.save('brands/logo-test.txt', ContentFile(b'logo'))
        response = api_client.get(f'/media/{relative}')
        assert response.status_code == status.HTTP_200_OK
        body = b''.join(response.streaming_content) if response.streaming else response.content
        assert body == b'logo'

    def test_public_media_is_not_served_when_debug_and_serve_media_are_off(
        self, api_client, settings
    ):
        settings.DEBUG = False
        settings.SERVE_MEDIA = False
        relative = default_storage.save('brands/hidden.txt', ContentFile(b'secret'))
        response = api_client.get(f'/media/{relative}')
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
class TestDownloadEndpointPermissions:
    def test_anonymous_receives_401_or_403(self, api_client):
        schematic_file = SchematicFileFactory()
        url = reverse('schematics:schematic-file-download', kwargs={'pk': schematic_file.pk})
        response = api_client.get(url)
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

    def test_authenticated_user_without_entitlement_is_forbidden(self, api_client):
        user = UserFactory()
        schematic_file = SchematicFileFactory()
        api_client.force_authenticate(user=user)
        url = reverse('schematics:schematic-file-download', kwargs={'pk': schematic_file.pk})
        response = api_client.get(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_subscriber_can_download_bytes(self, api_client):
        user = UserFactory()
        UserSubscriptionFactory(user=user)
        schematic_file = SchematicFileFactory()
        api_client.force_authenticate(user=user)
        url = reverse('schematics:schematic-file-download', kwargs={'pk': schematic_file.pk})
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        content = b''.join(response.streaming_content)
        assert content == MINIMAL_PDF_BYTES

    def test_purchaser_can_download_without_subscription(self, api_client):
        user = UserFactory()
        schematic_file = SchematicFileFactory()
        SchematicPurchaseFactory(user=user, schematic=schematic_file.schematic)
        api_client.force_authenticate(user=user)
        url = reverse('schematics:schematic-file-download', kwargs={'pk': schematic_file.pk})
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK

    def test_free_schematic_downloadable_without_subscription(self, api_client):
        user = UserFactory()
        schematic_file = SchematicFileFactory(schematic__is_free=True)
        api_client.force_authenticate(user=user)
        url = reverse('schematics:schematic-file-download', kwargs={'pk': schematic_file.pk})
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK

    def test_unknown_file_id_returns_404(self, api_client):
        user = UserFactory()
        api_client.force_authenticate(user=user)
        url = reverse('schematics:schematic-file-download', kwargs={'pk': 999_999})
        response = api_client.get(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND
