"""Protected inline/attachment streaming for schematic binaries."""

from __future__ import annotations

import os

from django.http import FileResponse
from rest_framework import status
from rest_framework.response import Response
from django.utils.translation import gettext_lazy as _


def open_schematic_file(schematic_file):
    """
    Open the stored binary or return an error Response.

    Callers must already have passed the access matrix.
    """
    if not schematic_file.file:
        return None, Response(
            {'detail': _('فایل فیزیکی روی سرور موجود نیست.')},
            status=status.HTTP_404_NOT_FOUND,
        )
    try:
        return schematic_file.file.open('rb'), None
    except (FileNotFoundError, OSError, ValueError):
        return None, Response(
            {'detail': _('فایل فیزیکی روی سرور موجود نیست.')},
            status=status.HTTP_404_NOT_FOUND,
        )


def stream_schematic_file(schematic_file, *, as_attachment: bool) -> FileResponse:
    """Stream bytes with headers that never advertise a public MEDIA path."""
    file_handle, error = open_schematic_file(schematic_file)
    if error:
        return error

    filename = os.path.basename(schematic_file.file.name)
    response = FileResponse(
        file_handle,
        as_attachment=as_attachment,
        filename=filename,
    )
    disposition = 'attachment' if as_attachment else 'inline'
    response['Content-Disposition'] = f'{disposition}; filename="{filename}"'
    response['Cache-Control'] = 'private, no-store, no-cache, must-revalidate'
    response['X-Content-Type-Options'] = 'nosniff'
    return response
