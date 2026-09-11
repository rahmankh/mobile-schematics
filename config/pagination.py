"""
Shared DRF pagination for catalog and other list endpoints.

PageNumberPagination keeps URLs bookmarkable (`?page=2`) which is easier for
mobile clients than opaque cursor tokens. `page_size` is client-tunable but
capped so a mistaken `page_size=99999` cannot dump the whole catalog.
"""

from __future__ import annotations

from rest_framework.pagination import PageNumberPagination


class StandardResultsSetPagination(PageNumberPagination):
    """Default page size 20; clients may pass `page_size` up to 100."""

    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100
