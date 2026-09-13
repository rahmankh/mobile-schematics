"""
Header catalog navigation.

The HTML chrome (dropdown + mobile drawer) needs brands and a few popular
models on every page. Keep the query here so the context processor stays thin
and tests can exercise the grouping without rendering templates.
"""

from __future__ import annotations

from collections import defaultdict

from django.db.models import Count

from schematics.models import Brand, PhoneModel

POPULAR_MODELS_PER_BRAND = 6
AUTH_URL_NAMES = frozenset(
    {
        'login',
        'register',
        'password-reset',
        'password-reset-confirm',
    }
)
_SKIP_PREFIXES = ('/admin/', '/api/', '/i18n/')


def is_auth_page(request) -> bool:
    """True on session login/register/password-reset HTML views."""
    match = getattr(request, 'resolver_match', None)
    url_name = getattr(match, 'url_name', None)
    return url_name in AUTH_URL_NAMES


def should_skip_catalog_nav(request) -> bool:
    """Admin/API/i18n renders should not pay for the catalog menu query."""
    path = getattr(request, 'path', '') or ''
    return path.startswith(_SKIP_PREFIXES)


def build_nav_brands() -> list[Brand]:
    """
    Brands with up to POPULAR_MODELS_PER_BRAND models each.

    Popularity is schematic count (then name). Each brand gets a
    `popular_models` list attribute; missing data returns an empty list.
    """
    brands = list(Brand.objects.order_by('name'))
    if not brands:
        return []

    models = (
        PhoneModel.objects.filter(brand_id__in=[brand.pk for brand in brands])
        .annotate(schematics_count=Count('schematics'))
        .order_by('brand_id', '-schematics_count', 'name')
    )
    by_brand: dict[int, list[PhoneModel]] = defaultdict(list)
    for model in models:
        bucket = by_brand[model.brand_id]
        if len(bucket) < POPULAR_MODELS_PER_BRAND:
            bucket.append(model)

    for brand in brands:
        brand.popular_models = by_brand.get(brand.pk, [])
    return brands
