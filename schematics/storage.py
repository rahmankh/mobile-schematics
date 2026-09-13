"""
Private filesystem storage for paid schematic binaries.

Paid PDFs / boardviews must never be reachable via MEDIA_URL. This storage
points at settings.PROTECTED_MEDIA_ROOT (a directory outside MEDIA_ROOT) and
refuses to generate a public URL so serializers and templates cannot leak a
direct download path.
"""

from __future__ import annotations

import os

from django.conf import settings
from django.core.files.storage import FileSystemStorage


class ProtectedSchematicStorage(FileSystemStorage):
    """
    FileSystemStorage variant that keeps schematic files off the public media tree.

    Why a custom class instead of default_storage?
    - default_storage writes into MEDIA_ROOT, which Django (DEBUG) and nginx
      (production) typically serve as static downloads with no auth check.
    - location is resolved from settings at access time so pytest can point
      PROTECTED_MEDIA_ROOT at a temporary directory without re-importing this module.
    """

    def __init__(self, location=None, base_url='', **kwargs):
        # base_url is intentionally blank: there is no public HTTP prefix for these files.
        # location stays None by default so `base_location` reads live settings.
        super().__init__(location=location, base_url=base_url, **kwargs)

    def deconstruct(self):
        """
        Keep migrations path-agnostic.

        Baking the absolute PROTECTED_MEDIA_ROOT into migrations would break
        every machine (Windows vs Linux, CI tmp dirs, etc.).
        """
        return ('schematics.storage.ProtectedSchematicStorage', [], {})

    @property
    def base_location(self) -> str:
        if self._location:
            return str(self._location)
        return str(settings.PROTECTED_MEDIA_ROOT)

    @property
    def location(self) -> str:
        return os.path.abspath(self.base_location)

    def url(self, name: str) -> str:
        """
        Block accidental public URL generation.

        Clients must reverse `schematics:schematic-file-view` instead.
        """
        raise ValueError(
            "Protected schematic files are not publicly addressable. "
            "Use the authenticated download API instead."
        )


# Singleton used by SchematicFile.file. Tests may rely on live settings.PROTECTED_MEDIA_ROOT.
protected_storage = ProtectedSchematicStorage()
