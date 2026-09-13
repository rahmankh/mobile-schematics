"""Header catalog navigation: brands dropdown data and context processor."""

from __future__ import annotations

import pytest
from django.conf import settings
from django.test import RequestFactory
from django.urls import reverse

from schematics.factories import BrandFactory, PhoneModelFactory, SchematicFactory
from web.context_processors import catalog_nav
from web.nav import POPULAR_MODELS_PER_BRAND, build_nav_brands, is_auth_page


@pytest.mark.django_db
class TestBuildNavBrands:
    def test_empty_catalog_returns_empty_list(self):
        assert build_nav_brands() == []

    def test_groups_popular_models_under_each_brand(self):
        samsung = BrandFactory(name='Samsung', slug='samsung')
        apple = BrandFactory(name='Apple', slug='apple')
        PhoneModelFactory(brand=samsung, name='Galaxy S24 Ultra', slug='galaxy-s24-ultra')
        PhoneModelFactory(brand=apple, name='iPhone 15 Pro', slug='iphone-15-pro')

        nav = build_nav_brands()

        assert [brand.name for brand in nav] == ['Apple', 'Samsung']
        apple_nav, samsung_nav = nav
        assert [model.name for model in apple_nav.popular_models] == ['iPhone 15 Pro']
        assert [model.name for model in samsung_nav.popular_models] == ['Galaxy S24 Ultra']

    def test_orders_models_by_schematic_count_and_caps_per_brand(self):
        brand = BrandFactory(name='Xiaomi', slug='xiaomi')
        models = [
            PhoneModelFactory(brand=brand, name=f'Model {index}', slug=f'model-{index}')
            for index in range(POPULAR_MODELS_PER_BRAND + 2)
        ]
        popular = models[-1]
        SchematicFactory(phone_model=popular)
        SchematicFactory(phone_model=popular)

        nav = build_nav_brands()

        assert len(nav) == 1
        names = [model.name for model in nav[0].popular_models]
        assert len(names) == POPULAR_MODELS_PER_BRAND
        assert names[0] == popular.name


class TestCatalogNavContextProcessor:
    def test_processor_is_registered(self):
        processors = settings.TEMPLATES[0]['OPTIONS']['context_processors']
        assert 'web.context_processors.catalog_nav' in processors

    def test_skips_admin_and_api_paths(self):
        factory = RequestFactory()
        assert catalog_nav(factory.get('/admin/')) == {}
        assert catalog_nav(factory.get('/api/v1/schematics/')) == {}

    @pytest.mark.django_db
    def test_exposes_nav_brands_and_auth_flag(self):
        BrandFactory(name='Samsung', slug='samsung')
        request = RequestFactory().get('/')
        request.resolver_match = type('Match', (), {'url_name': 'home'})()

        data = catalog_nav(request)

        assert data['is_auth_page'] is False
        assert [brand.name for brand in data['nav_brands']] == ['Samsung']

    def test_is_auth_page_for_login_and_register(self):
        request = RequestFactory().get('/login/')
        request.resolver_match = type('Match', (), {'url_name': 'login'})()
        assert is_auth_page(request) is True
        request.resolver_match = type('Match', (), {'url_name': 'register'})()
        assert is_auth_page(request) is True
        request.resolver_match = type('Match', (), {'url_name': 'home'})()
        assert is_auth_page(request) is False


@pytest.mark.django_db
class TestHeaderBrandMenu:
    def test_home_header_dropdown_lists_brand_and_popular_model(self, client):
        brand = BrandFactory(name='Samsung', slug='samsung')
        PhoneModelFactory(brand=brand, name='Galaxy S24 Ultra', slug='galaxy-s24-ultra')

        html = client.get(reverse('web:home')).content.decode('utf-8')

        assert 'dropdown' in html
        assert 'drawer' in html
        assert 'Galaxy S24 Ultra' in html
        assert reverse('web:brand-detail', kwargs={'slug': 'samsung'}) in html
        assert reverse(
            'web:model-detail',
            kwargs={'brand_slug': 'samsung', 'model_slug': 'galaxy-s24-ultra'},
        ) in html

    def test_empty_catalog_hides_brands_dropdown(self, client):
        html = client.get(reverse('web:home')).content.decode('utf-8')

        assert 'nav-dropdown' not in html
        assert 'برندی برای نمایش نیست' in html
        assert 'class="btn btn-ghost" href="{0}">ورود</a>'.format(reverse('web:login')) in html
