"""
Public media serving with an explicit deny-list for protected schematic files.

In production, nginx/CDN should serve MEDIA_ROOT and never alias PROTECTED_MEDIA_ROOT.
This view is the Django safety net used in DEBUG, tests, and misconfigured deploys:
it serves brand logos and other public uploads, but never `protected_schematics/`.
"""

from __future__ import annotations

from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse
from django.views.static import serve


PROTECTED_MEDIA_PREFIX = 'protected_schematics/'


def serve_public_media(request: HttpRequest, path: str) -> HttpResponse:
    """
    Serve a file from MEDIA_ROOT after rejecting protected schematic paths.

    Path traversal is handled by django.views.static.serve (safe_join).
    When both DEBUG and SERVE_MEDIA are False, nothing is served from Django;
    the 404 matches a production app that leaves media to the reverse proxy.
    """
    normalized = path.replace('\\', '/').lstrip('/')

    # Defence in depth: refuse the protected prefix even if a file exists on disk.
    if (
        normalized.startswith(PROTECTED_MEDIA_PREFIX)
        or f'/{PROTECTED_MEDIA_PREFIX}' in f'/{normalized}'
    ):
        raise Http404('Not found')

    if not (settings.DEBUG or getattr(settings, 'SERVE_MEDIA', False)):
        raise Http404('Not found')

    return serve(request, path, document_root=settings.MEDIA_ROOT)
