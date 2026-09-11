"""
Management command: seed_demo_data

Populates an empty (or sparse) database with realistic catalog rows so the
mobile UI can be exercised without manual admin entry.

The command is idempotent: brands/models/categories/schematics are get_or_create'd
by slug/title, and demo user passwords are reset to the documented values so
frontend testers can always log in.
"""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.utils import timezone

from schematics.models import (
    Brand,
    PhoneModel,
    Schematic,
    SchematicCategory,
    SchematicFile,
    SchematicPurchase,
)
from subscriptions.models import Plan, UserSubscription

User = get_user_model()

# Tiny but valid-enough PDF payload for UI download testing.
DEMO_PDF = b'%PDF-1.4\n1 0 obj<< /Type /Catalog >>endobj\ntrailer<<>>\n%%EOF\n'

DEMO_USERS = [
    {
        'phone_number': '09120000000',
        'password': 'AdminPass123!',
        'first_name': 'Admin',
        'last_name': 'Schematics',
        'repair_shop_name': 'HQ',
        'role': User.RoleChoices.ADMIN,
        'is_staff': True,
        'is_superuser': True,
    },
    {
        'phone_number': '09121111111',
        'password': 'TechPass123!',
        'first_name': 'Ali',
        'last_name': 'Karimi',
        'repair_shop_name': 'Tehran Mobile Fix',
        'role': User.RoleChoices.TECHNICIAN,
        'is_staff': False,
        'is_superuser': False,
    },
    {
        'phone_number': '09122222222',
        'password': 'SubPass123!',
        'first_name': 'Sara',
        'last_name': 'Mohammadi',
        'repair_shop_name': 'Isfahan Repair Lab',
        'role': User.RoleChoices.TECHNICIAN,
        'is_staff': False,
        'is_superuser': False,
    },
    {
        'phone_number': '09123333333',
        'password': 'BuyPass123!',
        'first_name': 'Reza',
        'last_name': 'Nouri',
        'repair_shop_name': 'Shiraz Phone Service',
        'role': User.RoleChoices.TECHNICIAN,
        'is_staff': False,
        'is_superuser': False,
    },
]

BRANDS = [
    {'name': 'Samsung', 'slug': 'samsung'},
    {'name': 'Xiaomi', 'slug': 'xiaomi'},
    {'name': 'Apple', 'slug': 'apple'},
    {'name': 'Huawei', 'slug': 'huawei'},
    {'name': 'Nokia', 'slug': 'nokia'},
    {'name': 'Motorola', 'slug': 'motorola'},
]

PHONE_MODELS = [
    {'brand': 'samsung', 'name': 'Galaxy S24 Ultra', 'slug': 'galaxy-s24-ultra', 'technical_code': 'SM-S928B'},
    {'brand': 'samsung', 'name': 'Galaxy A55', 'slug': 'galaxy-a55', 'technical_code': 'SM-A556E'},
    {'brand': 'samsung', 'name': 'Galaxy A15', 'slug': 'galaxy-a15', 'technical_code': 'SM-A155F'},
    {'brand': 'xiaomi', 'name': 'Redmi Note 13 Pro', 'slug': 'redmi-note-13-pro', 'technical_code': '23117RA68G'},
    {'brand': 'xiaomi', 'name': 'Poco F6', 'slug': 'poco-f6', 'technical_code': '24069PC21G'},
    {'brand': 'xiaomi', 'name': 'Xiaomi 14 Ultra', 'slug': 'xiaomi-14-ultra', 'technical_code': '24031PN0DC'},
    {'brand': 'apple', 'name': 'iPhone 15 Pro', 'slug': 'iphone-15-pro', 'technical_code': 'A3102'},
    {'brand': 'apple', 'name': 'iPhone 13', 'slug': 'iphone-13', 'technical_code': 'A2633'},
    {'brand': 'huawei', 'name': 'Pura 70', 'slug': 'pura-70', 'technical_code': 'ADY-LX9'},
    {'brand': 'nokia', 'name': 'G42', 'slug': 'g42', 'technical_code': 'TA-1582'},
    {'brand': 'motorola', 'name': 'Edge 50', 'slug': 'edge-50', 'technical_code': 'XT2405-1'},
]

CATEGORIES = [
    {
        'title': 'نقشه کامل برد',
        'slug': 'full-schematic',
        'description': 'نقشه کامل مدار مادربرد شامل آی‌سی‌ها و مسیرهای تغذیه.',
    },
    {
        'title': 'Boardview',
        'slug': 'boardview',
        'description': 'لایه کامپوننت و نت‌نیم برای پیدا کردن تست‌پوینت.',
    },
    {
        'title': 'مسیر ولتاژ',
        'slug': 'voltage-rails',
        'description': 'ریل‌های تغذیه PMIC، شارژ و RF.',
    },
    {
        'title': 'سرویس منوال',
        'slug': 'service-manual',
        'description': 'راهنمای سرویس رسمی / نیمه رسمی تعمیرکاران.',
    },
    {
        'title': 'تست‌پوینت',
        'slug': 'test-points',
        'description': 'نقاط اندازه‌گیری ولتاژ و مقاومت روی برد.',
    },
]

# (model_slug, category_slug, title, is_free, price, requires_subscription)
SCHEMATICS = [
    ('galaxy-s24-ultra', 'full-schematic', 'S24 Ultra Main Board Schematic', False, 280000, True),
    ('galaxy-s24-ultra', 'boardview', 'S24 Ultra Boardview (top/bottom)', False, 180000, True),
    ('galaxy-s24-ultra', 'voltage-rails', 'S24 Ultra PMIC & Charge Rails', True, 0, False),
    ('galaxy-a55', 'full-schematic', 'A55 Full Schematic', False, 120000, True),
    ('galaxy-a55', 'test-points', 'A55 Charge Test Points', True, 0, False),
    ('galaxy-a15', 'boardview', 'A15 Boardview', False, 90000, True),
    ('redmi-note-13-pro', 'full-schematic', 'Note 13 Pro Main Schematic', False, 140000, True),
    ('redmi-note-13-pro', 'voltage-rails', 'Note 13 Pro Display Power Rail', False, 70000, False),
    ('poco-f6', 'boardview', 'Poco F6 Boardview', False, 110000, True),
    ('xiaomi-14-ultra', 'full-schematic', '14 Ultra Full Schematic', False, 260000, True),
    ('iphone-15-pro', 'full-schematic', 'iPhone 15 Pro Logic Board', False, 320000, True),
    ('iphone-15-pro', 'service-manual', 'iPhone 15 Pro Service Manual (excerpt)', False, 150000, True),
    ('iphone-13', 'boardview', 'iPhone 13 Boardview', False, 130000, True),
    ('iphone-13', 'test-points', 'iPhone 13 FaceID Test Points', True, 0, False),
    ('pura-70', 'full-schematic', 'Pura 70 Main Schematic', False, 160000, True),
    ('g42', 'boardview', 'Nokia G42 Boardview', False, 60000, True),
    ('edge-50', 'voltage-rails', 'Edge 50 Charge Rail', False, 80000, True),
]

PLANS = [
    {
        'title': 'یک‌ماهه تکنسین',
        'description': 'دسترسی به تمام شماتیک‌های اشتراکی به مدت ۳۰ روز.',
        'price': 250000,
        'duration_days': 30,
    },
    {
        'title': 'سه‌ماهه حرفه‌ای',
        'description': '۹۰ روز دسترسی کامل — مناسب تعمیرگاه‌های شلوغ.',
        'price': 650000,
        'duration_days': 90,
    },
    {
        'title': 'یک‌ساله تعمیرگاه',
        'description': '۳۶۵ روز دسترسی نامحدود به آرشیو اشتراکی.',
        'price': 2100000,
        'duration_days': 365,
    },
]


class Command(BaseCommand):
    """Load demo catalog, users, plans, and a sample purchase for local UI work."""

    help = (
        'Seed brands, phone models, categories, dummy schematic PDFs, demo users, '
        'and subscription plans for local / UI testing.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--no-files',
            action='store_true',
            help='Skip creating dummy PDF attachments (catalog rows only).',
        )

    def handle(self, *args, **options):
        skip_files = options['no_files']
        brands = self._seed_brands()
        models = self._seed_phone_models(brands)
        categories = self._seed_categories()
        schematics = self._seed_schematics(models, categories, skip_files=skip_files)
        users = self._seed_users()
        plans = self._seed_plans()
        self._seed_entitlements(users, plans, schematics)

        self.stdout.write(self.style.SUCCESS('Demo data is ready.'))
        self.stdout.write('')
        self.stdout.write('Demo logins (phone / password):')
        for row in DEMO_USERS:
            self.stdout.write(f"  {row['phone_number']}  /  {row['password']}")

    def _seed_brands(self) -> dict[str, Brand]:
        created = {}
        for row in BRANDS:
            brand, _ = Brand.objects.get_or_create(
                slug=row['slug'],
                defaults={'name': row['name']},
            )
            created[row['slug']] = brand
        self.stdout.write(f'Brands: {len(created)}')
        return created

    def _seed_phone_models(self, brands: dict[str, Brand]) -> dict[str, PhoneModel]:
        created = {}
        for row in PHONE_MODELS:
            phone_model, _ = PhoneModel.objects.get_or_create(
                brand=brands[row['brand']],
                slug=row['slug'],
                defaults={
                    'name': row['name'],
                    'technical_code': row['technical_code'],
                },
            )
            created[row['slug']] = phone_model
        self.stdout.write(f'Phone models: {len(created)}')
        return created

    def _seed_categories(self) -> dict[str, SchematicCategory]:
        created = {}
        for row in CATEGORIES:
            category, _ = SchematicCategory.objects.get_or_create(
                slug=row['slug'],
                defaults={
                    'title': row['title'],
                    'description': row['description'],
                },
            )
            created[row['slug']] = category
        self.stdout.write(f'Categories: {len(created)}')
        return created

    def _seed_schematics(
        self,
        models: dict[str, PhoneModel],
        categories: dict[str, SchematicCategory],
        *,
        skip_files: bool,
    ) -> list[Schematic]:
        created = []
        for model_slug, category_slug, title, is_free, price, requires_sub in SCHEMATICS:
            schematic, _ = Schematic.objects.get_or_create(
                phone_model=models[model_slug],
                category=categories[category_slug],
                title=title,
                defaults={
                    'description': (
                        f'Demo troubleshooting notes for {title}. '
                        'Check PMIC output, coil continuity, and shorted rails before replacing ICs.'
                    ),
                    'is_free': is_free,
                    'price': price,
                    'requires_subscription': requires_sub,
                },
            )
            if not skip_files and not schematic.files.exists():
                attachment = SchematicFile(schematic=schematic, file_title=f'{title} PDF')
                filename = f'{model_slug}-{category_slug}.pdf'
                attachment.file.save(filename, ContentFile(DEMO_PDF), save=True)
            created.append(schematic)
        self.stdout.write(f'Schematics: {len(created)}')
        return created

    def _seed_users(self) -> dict[str, User]:
        created = {}
        for row in DEMO_USERS:
            defaults = {k: v for k, v in row.items() if k not in ('phone_number', 'password')}
            user, _ = User.objects.get_or_create(
                phone_number=row['phone_number'],
                defaults=defaults,
            )
            # Keep documented passwords in sync for UI testers on every run.
            for field, value in defaults.items():
                setattr(user, field, value)
            user.set_password(row['password'])
            user.save()
            created[row['phone_number']] = user
        self.stdout.write(f'Users: {len(created)}')
        return created

    def _seed_plans(self) -> dict[str, Plan]:
        created = {}
        for row in PLANS:
            plan, _ = Plan.objects.get_or_create(
                title=row['title'],
                defaults={
                    'description': row['description'],
                    'price': row['price'],
                    'duration_days': row['duration_days'],
                    'is_active': True,
                },
            )
            created[row['title']] = plan
        self.stdout.write(f'Plans: {len(created)}')
        return created

    def _seed_entitlements(
        self,
        users: dict[str, User],
        plans: dict[str, Plan],
        schematics: list[Schematic],
    ) -> None:
        """Give one demo technician an active plan and another a single-copy purchase."""
        subscriber = users['09122222222']
        monthly = plans['یک‌ماهه تکنسین']
        if not UserSubscription.objects.has_active_subscription(subscriber):
            now = timezone.now()
            UserSubscription.objects.create(
                user=subscriber,
                plan=monthly,
                start_date=now,
                end_date=now + timedelta(days=monthly.duration_days),
                status=UserSubscription.StatusChoices.ACTIVE,
            )

        buyer = users['09123333333']
        paid = next((item for item in schematics if not item.is_free), schematics[0])
        SchematicPurchase.objects.get_or_create(
            user=buyer,
            schematic=paid,
            defaults={'price_paid': paid.price},
        )
