"""HTML catalog pages: header auth, brands, models, and schematic detail."""

from __future__ import annotations

import pytest
from django.urls import reverse

from django.template.defaultfilters import filesizeformat

from schematics.models import SchematicPurchase
from schematics.factories import (
    BrandFactory,
    PhoneModelFactory,
    SchematicCategoryFactory,
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
        assert reverse('web:register') in html
        assert 'ثبت‌نام' in html

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

    def test_schematic_page_asks_guests_to_log_in_for_viewer(self, client):
        schematic_file = SchematicFileFactory(file_title='Board PDF')
        url = reverse('web:schematic-detail', kwargs={'pk': schematic_file.schematic.pk})

        html = client.get(url).content.decode('utf-8')

        assert schematic_file.file_title in html
        assert 'برای مشاهده وارد شوید' in html
        assert reverse('web:register') in html
        assert reverse(
            'schematics:schematic-file-download', kwargs={'pk': schematic_file.pk}
        ) not in html
        assert reverse(
            'schematics:schematic-file-view', kwargs={'pk': schematic_file.pk}
        ) not in html

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
        assert reverse('web:register') in guest_home

    def test_register_page_is_linked_from_login(self, client):
        html = client.get(reverse('web:login')).content.decode('utf-8')
        assert reverse('web:register') in html
        assert 'ثبت‌نام' in html
        assert 'تکنسین' not in html
        assert reverse('web:password-reset') in html
        assert 'رمز عبور را فراموش کرده‌اید؟' in html

    def test_login_and_register_headers_offer_home_instead_of_auth_buttons(self, client):
        login_url = reverse('web:login')
        register_url = reverse('web:register')
        home_url = reverse('web:home')
        header_login = f'class="btn btn-ghost" href="{login_url}">ورود</a>'
        header_register = f'class="btn btn-primary" href="{register_url}">ثبت‌نام</a>'

        login_html = client.get(login_url).content.decode('utf-8')
        assert 'بازگشت به صفحه اصلی' in login_html
        assert f'href="{home_url}"' in login_html
        assert header_login not in login_html
        assert header_register not in login_html
        assert 'ثبت‌نام' in login_html
        assert 'تکنسین' not in login_html

        register_html = client.get(register_url).content.decode('utf-8')
        assert 'بازگشت به صفحه اصلی' in register_html
        assert f'href="{home_url}"' in register_html
        assert header_login not in register_html
        assert header_register not in register_html
        assert 'حساب دارید؟' in register_html

    def test_technician_can_register_from_html_and_is_logged_in(self, client):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        response = client.post(
            reverse('web:register'),
            {
                'phone_number': '+989123000888',
                'first_name': 'Nima',
                'last_name': 'Rezaei',
                'repair_shop_name': 'Tabriz Shop',
                'password': 'StrongPassword@123',
                'password_confirm': 'StrongPassword@123',
                'role': 'admin',
                'is_staff': True,
            },
        )
        assert response.status_code == 302
        user = User.objects.get(phone_number='09123000888')
        assert user.role == User.RoleChoices.TECHNICIAN
        assert user.is_staff is False
        assert user.check_password('StrongPassword@123')
        home = client.get(reverse('web:home'))
        assert user.phone_number in home.content.decode('utf-8')
        assert 'خروج' in home.content.decode('utf-8')

    def test_register_rejects_duplicate_phone(self, client):
        UserFactory(phone_number='09123000889', password='StrongPassword@123')
        response = client.post(
            reverse('web:register'),
            {
                'phone_number': '09123000889',
                'password': 'StrongPassword@123',
                'password_confirm': 'StrongPassword@123',
            },
        )
        assert response.status_code == 200
        assert 'قبلاً ثبت‌نام' in response.content.decode('utf-8')

    def test_profile_requires_login(self, client):
        response = client.get(reverse('web:profile'))
        assert response.status_code == 302
        assert reverse('web:login') in response.url

    def test_profile_shows_wallet_instead_of_subscription(self, client):
        user = UserFactory(first_name='Sara', repair_shop_name='Isfahan Lab', wallet_balance=75000)
        UserSubscriptionFactory(user=user)
        client.force_login(user)

        html = client.get(reverse('web:profile')).content.decode('utf-8')

        assert 'Sara' in html
        assert 'Isfahan Lab' in html
        assert user.phone_number in html
        assert 'شارژ کیف پول' in html
        assert '75000' in html or '۷۵' in html
        assert 'اشتراک فعال ندارید' not in html
        assert 'تکنسین' not in html

    def test_home_search_filters_schematics_and_keeps_auth_header(self, client):
        SchematicFactory(title='Main Board')
        SchematicFactory(title='UniqueXyz Voltage')

        html = client.get(reverse('web:home'), {'q': 'UniqueXyz'}).content.decode('utf-8')

        assert 'UniqueXyz Voltage' in html
        assert 'Main Board' not in html
        assert 'نتایج شماتیک' in html
        assert 'class="btn btn-ghost" href="{0}">ورود</a>'.format(reverse('web:login')) in html
        assert 'class="btn btn-primary" href="{0}">ثبت‌نام</a>'.format(reverse('web:register')) in html

    def test_home_access_filter_hides_free_when_asking_for_paid(self, client):
        SchematicFactory(title='Open Board', is_free=True, requires_subscription=False, price=0)
        SchematicFactory(title='Locked Board', is_free=False, requires_subscription=True)

        html = client.get(reverse('web:home'), {'access': 'paid'}).content.decode('utf-8')

        assert 'Locked Board' in html
        assert 'Open Board' not in html

    def test_schematic_cards_show_file_size_and_access_badges(self, client):
        category = SchematicCategoryFactory(title='Boardview', slug='boardview')
        free_file = SchematicFileFactory(
            schematic__title='Free Rail Map',
            schematic__is_free=True,
            schematic__requires_subscription=False,
            schematic__price=0,
            schematic__category=category,
            file_title='Free PDF',
        )
        SchematicFactory(
            title='Gated Rail Map',
            is_free=False,
            requires_subscription=True,
            price=150000,
            category=category,
        )

        html = client.get(reverse('web:home')).content.decode('utf-8')

        assert 'رایگان' in html
        assert 'خرید تکی' in html
        assert 'اشتراکی' not in html
        assert filesizeformat(free_file.file_size_bytes) in html

    def test_catalog_pages_load_vazirmatn_and_omit_technician_copy(self, client):
        html = client.get(reverse('web:home')).content.decode('utf-8')
        assert 'Vazirmatn' in html
        assert 'تکنسین' not in html
        assert 'dir="rtl"' in html

    def test_wallet_pay_from_schematic_page(self, client):
        user = UserFactory(wallet_balance=200000)
        schematic = SchematicFactory(is_free=False, price=150000, title='Paid Board')
        SchematicFileFactory(schematic=schematic)
        client.force_login(user)

        html = client.get(
            reverse('web:schematic-detail', kwargs={'pk': schematic.pk})
        ).content.decode('utf-8')
        assert 'خرید تکی' in html
        assert 'پرداخت از کیف پول' in html
        assert 'اشتراکی' not in html
        assert 'با اشتراک' not in html

        response = client.post(reverse('web:wallet-pay-schematic', kwargs={'pk': schematic.pk}))
        assert response.status_code == 302
        user.refresh_from_db()
        assert user.wallet_balance == 50000
        bought = client.get(reverse('web:schematic-detail', kwargs={'pk': schematic.pk}))
        html = bought.content.decode('utf-8')
        schematic_file = schematic.files.first()
        assert reverse(
            'schematics:schematic-file-view', kwargs={'pk': schematic_file.pk}
        ) in html
        assert reverse(
            'schematics:schematic-file-download', kwargs={'pk': schematic_file.pk}
        ) not in html
        assert 'schematic-viewer' in html
        assert 'دانلود فایل خام غیرفعال است' in html
        assert 'viewer.js' in html
        assert user.phone_number in html

    def test_single_purchase_mock_checkout_fulfills_after_verify_redirect(self, client):
        user = UserFactory()
        schematic = SchematicFactory(is_free=False, price=150000, title='Gateway Board')
        SchematicFileFactory(schematic=schematic)
        client.force_login(user)

        start = client.post(reverse('web:schematic-checkout', kwargs={'pk': schematic.pk}))
        assert start.status_code == 302
        location = start['Location']
        assert 'Authority=S.' in location
        assert 'zarinpal.com' not in location

        verify = client.get(location)
        assert verify.status_code == 200
        assert verify.json()['paid'] is True
        assert SchematicPurchase.objects.filter(user=user, schematic=schematic).exists()

        html = client.get(
            reverse('web:schematic-detail', kwargs={'pk': schematic.pk})
        ).content.decode('utf-8')
        assert 'schematic-viewer' in html


@pytest.mark.django_db
class TestCartBatchCheckout:
    def test_add_two_items_then_batch_checkout_grants_both_viewers(self, client):
        user = UserFactory()
        first = SchematicFactory(is_free=False, price=80000, title='Cart Board A')
        second = SchematicFactory(is_free=False, price=70000, title='Cart Board B')
        SchematicFileFactory(schematic=first, file_title='A PDF')
        SchematicFileFactory(schematic=second, file_title='B PDF')
        client.force_login(user)

        add_first = client.post(
            reverse('web:cart-add', kwargs={'pk': first.pk}),
            {'next': reverse('web:schematic-detail', kwargs={'pk': first.pk})},
        )
        assert add_first.status_code == 302
        client.post(reverse('web:cart-add', kwargs={'pk': second.pk}))
        client.post(reverse('web:cart-add', kwargs={'pk': first.pk}))

        cart = client.get(reverse('web:cart'))
        html = cart.content.decode('utf-8')
        assert cart.status_code == 200
        assert 'Cart Board A' in html
        assert 'Cart Board B' in html
        assert '150000' in html
        assert 'پرداخت یکجای سبد' in html
        assert '>2</span>' in html or 'cart-count' in html

        start = client.post(reverse('web:cart-checkout'))
        assert start.status_code == 302
        location = start['Location']
        assert 'Authority=S.' in location
        assert 'zarinpal.com' not in location

        verify = client.get(location)
        assert verify.status_code == 200
        payload = verify.json()
        assert payload['paid'] is True
        assert sorted(payload['schematic_ids']) == sorted([first.pk, second.pk])
        assert SchematicPurchase.objects.filter(user=user).count() == 2

        first_page = client.get(
            reverse('web:schematic-detail', kwargs={'pk': first.pk})
        ).content.decode('utf-8')
        second_page = client.get(
            reverse('web:schematic-detail', kwargs={'pk': second.pk})
        ).content.decode('utf-8')
        assert 'schematic-viewer' in first_page
        assert 'schematic-viewer' in second_page
        assert reverse(
            'schematics:schematic-file-view', kwargs={'pk': first.files.first().pk}
        ) in first_page
        assert reverse(
            'schematics:schematic-file-download', kwargs={'pk': first.files.first().pk}
        ) not in first_page

        emptied = client.get(reverse('web:cart')).content.decode('utf-8')
        assert 'سبد خرید خالی است' in emptied

    def test_cart_add_rejects_free_schematic(self, client):
        user = UserFactory()
        schematic = SchematicFactory(is_free=True, price=0, title='Open Board')
        client.force_login(user)

        response = client.post(reverse('web:cart-add', kwargs={'pk': schematic.pk}))
        assert response.status_code == 302
        cart = client.get(reverse('web:cart')).content.decode('utf-8')
        assert 'سبد خرید خالی است' in cart

    def test_guest_can_fill_cart_but_checkout_requires_login(self, client):
        schematic = SchematicFactory(is_free=False, price=110000, title='Guest Cart Board')
        added = client.post(reverse('web:cart-add', kwargs={'pk': schematic.pk}))
        assert added.status_code == 302
        html = client.get(reverse('web:cart')).content.decode('utf-8')
        assert 'Guest Cart Board' in html
        assert 'برای پرداخت وارد شوید' in html

        checkout = client.post(reverse('web:cart-checkout'))
        assert checkout.status_code == 302
        assert reverse('web:login') in checkout.url


@pytest.mark.django_db
class TestPasswordResetPages:
    def test_request_page_is_reachable(self, client):
        html = client.get(reverse('web:password-reset')).content.decode('utf-8')
        assert 'بازیابی رمز عبور' in html
        assert reverse('web:login') in html
        assert 'بازگشت به صفحه اصلی' in html
        assert 'class="btn btn-ghost" href="{0}">ورود</a>'.format(reverse('web:login')) not in html
        assert 'class="btn btn-primary" href="{0}">ثبت‌نام</a>'.format(reverse('web:register')) not in html

    def test_unknown_phone_still_reaches_confirm(self, client):
        response = client.post(
            reverse('web:password-reset'),
            {'phone_number': '09123000780'},
        )
        assert response.status_code == 302
        assert reverse('web:password-reset-confirm') in response.url
        follow = client.get(response.url)
        assert follow.status_code == 200
        assert 'اگر این شماره حساب داشته باشد' in follow.content.decode('utf-8')

    def test_technician_can_reset_password_from_html(self, client, monkeypatch):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        monkeypatch.setattr('accounts.password_reset.generate_otp', lambda: '847291')
        user = UserFactory(phone_number='09123000781', password='StrongPassword@123')

        request_response = client.post(
            reverse('web:password-reset'),
            {'phone_number': '09123000781'},
        )
        assert request_response.status_code == 302

        confirm = client.post(
            reverse('web:password-reset-confirm'),
            {
                'phone_number': '09123000781',
                'otp': '847291',
                'password': 'BrandNewPass@456',
                'password_confirm': 'BrandNewPass@456',
            },
        )
        assert confirm.status_code == 302
        assert reverse('web:login') in confirm.url
        user.refresh_from_db()
        assert user.check_password('BrandNewPass@456')
        assert user.check_password('StrongPassword@123') is False

        login_old = client.post(
            reverse('web:login'),
            {'username': '09123000781', 'password': 'StrongPassword@123'},
        )
        assert login_old.status_code == 200
        login_new = client.post(
            reverse('web:login'),
            {'username': '09123000781', 'password': 'BrandNewPass@456'},
        )
        assert login_new.status_code == 302
        home = client.get(reverse('web:home')).content.decode('utf-8')
        assert 'خروج' in home
        assert User.objects.get(phone_number='09123000781').phone_number in home

    def test_wrong_otp_stays_on_confirm(self, client, monkeypatch):
        monkeypatch.setattr('accounts.password_reset.generate_otp', lambda: '847291')
        UserFactory(phone_number='09123000782', password='StrongPassword@123')
        client.post(reverse('web:password-reset'), {'phone_number': '09123000782'})
        response = client.post(
            reverse('web:password-reset-confirm'),
            {
                'phone_number': '09123000782',
                'otp': '000000',
                'password': 'BrandNewPass@456',
                'password_confirm': 'BrandNewPass@456',
            },
        )
        assert response.status_code == 200
        assert 'کد بازیابی نامعتبر یا منقضی است' in response.content.decode('utf-8')

