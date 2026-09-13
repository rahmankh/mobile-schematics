"""Template context shared by the catalog chrome (header dropdown / drawer)."""

from __future__ import annotations

from .nav import build_nav_brands, is_auth_page, should_skip_catalog_nav


def catalog_nav(request) -> dict:
    """
    `nav_brands` plus `is_auth_page`.

    Empty catalogs fall back to `nav_brands=[]` so the header can hide the
    brands menu instead of rendering a broken dropdown.
    """
    if should_skip_catalog_nav(request):
        return {}
    return {
        'nav_brands': build_nav_brands(),
        'is_auth_page': is_auth_page(request),
    }
