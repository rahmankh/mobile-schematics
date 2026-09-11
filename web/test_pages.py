"""HTML catalog pages: header auth, brands, models, and schematic detail."""

from __future__ import annotations

import pytest
from django.urls import reverse

from schematics.factories import (
    BrandFactory,
    PhoneModelFactory,
    SchematicFactory,
    SchematicFileFactory,
    UserFactory,
    UserSubscriptionFactory,
)


@pytest.mark.django_db
class TestCatalogPages:
    def test_home_shows_brands_and_guest_login_in_header(self, client):
        BrandFactory(name='Samsung', slug='samsung')
        BrandFactory(name='Xiaomi', slug='xiaomi')

        response = client.get(reverse('web:home'))

        html = response.content.decode('utf-8')
        assert response.status_code == 200
        assert 'Samsung' in html
        assert 'Xiaomi' in html
        assert 'ورود' in html
        assert 'خروج' not in html
        assert reverse('web:login') in html

    def test_home_shows_sample_models_and_categories(self, client):
        brand = BrandFactory(name='Samsung', slug='samsung')
        PhoneModelFactory(brand=brand, name='Galaxy S24 Ultra', slug='galaxy-s24-ultra')
        SchematicFactory(title='Main Board')

        html = client.get(reverse('web:home')).content.decode('utf-8')

        assert 'Galaxy S24 Ultra' in html
        assert 'مدل‌های نمونه' in html
        assert 'دسته‌بندی نقشه‌ها' in html

    def test_authenticated_header_shows_phone_number_and_logout(self, client):
        user = UserFactory(first_name='Ali', last_name='Karimi')
        client.force_login(user)

        html = client.get(reverse('web:home')).content.decode('utf-8')

        assert 'Ali Karimi' in html
        assert user.phone_number in html
        assert 'خروج' in html
        assert reverse('web:profile') in html

    def test_brand_page_lists_phone_models(self, client):
        brand = BrandFactory(name='Apple', slug='apple')
        PhoneModelFactory(brand=brand, name='iPhone 15 Pro', slug='iphone-15-pro')

        response = client.get(reverse('web:brand-detail', kwargs={'slug': 'apple'}))
        html = response.content.decode('utf-8')

        assert response.status_code == 200
        assert 'iPhone 15 Pro' in html

    def test_model_page_lists_schematics(self, client):
        brand = BrandFactory(name='Samsung', slug='samsung')
        phone = PhoneModelFactory(brand=brand, name='Galaxy S24 Ultra', slug='galaxy-s24-ultra')
        SchematicFactory(phone_model=phone, title='S24 Ultra Main Board')

        response = client.get(
            reverse(
                'web:model-detail',
                kwargs={'brand_slug': 'samsung', 'model_slug': 'galaxy-s24-ultra'},
            )
        )

        assert response.status_code == 200
        assert 'S24 Ultra Main Board' in response.content.decode('utf-8')

    def test_schematic_page_asks_guests_to_log_in_for_download(self, client):
        schematic_file = SchematicFileFactory(file_title='Board PDF')
        url = reverse('web:schematic-detail', kwargs={'pk': schematic_file.schematic.pk})

        html = client.get(url).content.decode('utf-8')

        assert schematic_file.file_title in html
        assert 'برای دانلود وارد شوید' in html

    def test_login_then_logout_roundtrip(self, client):
        user = UserFactory(password='Password123!')

        login_response = client.post(
            reverse('web:login'),
            {'username': user.phone_number, 'password': 'Password123!'},
        )
        assert login_response.status_code == 302

        home = client.get(reverse('web:home')).content.decode('utf-8')
        assert 'خروج' in home

        logout_response = client.post(reverse('web:logout'))
        assert logout_response.status_code == 302
        guest_home = client.get(reverse('web:home')).content.decode('utf-8')
        assert 'ورود' in guest_home

    def test_profile_requires_login(self, client):
        response = client.get(reverse('web:profile'))
        assert response.status_code == 302
        assert reverse('web:login') in response.url

    def test_profile_shows_active_subscription(self, client):
        user = UserFactory(first_name='Sara', repair_shop_name='Isfahan Lab')
        UserSubscriptionFactory(user=user)
        client.force_login(user)

        html = client.get(reverse('web:profile')).content.decode('utf-8')

        assert 'Sara' in html
        assert 'Isfahan Lab' in html
        assert user.phone_number in html
