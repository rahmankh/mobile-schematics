"""
Shared pytest fixtures for the mobile-schematics test suite.

An autouse fixture isolates MEDIA_ROOT and PROTECTED_MEDIA_ROOT under tmp_path
so schematic PDFs never land in the developer's real media directories.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from rest_framework.test import APIClient


@pytest.fixture
def api_client() -> APIClient:
    """Unauthenticated DRF client. Tests call force_authenticate as needed."""
    return APIClient()


@pytest.fixture(autouse=True)
def _isolate_file_storage(settings, tmp_path: Path):
    """
    Point both public and protected storages at a per-test temp tree.

    ProtectedSchematicStorage reads PROTECTED_MEDIA_ROOT from settings at
    access time, so this fixture is enough — no need to patch the singleton.
    """
    media_root = tmp_path / 'media'
    protected_root = tmp_path / 'protected_media'
    media_root.mkdir()
    protected_root.mkdir()
    settings.MEDIA_ROOT = str(media_root)
    settings.PROTECTED_MEDIA_ROOT = str(protected_root)
    # Tests that hit /media/ must be able to exercise serve_public_media.
    settings.SERVE_MEDIA = True
    settings.DEBUG = True
    yield
