"""Tests for the seed_demo_data management command (idempotent UI fixtures)."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command

from schematics.models import Brand, Schematic, SchematicFile, SchematicPurchase
from subscriptions.models import Plan, UserSubscription

User = get_user_model()


@pytest.mark.django_db
class TestSeedDemoDataCommand:
    def test_seed_creates_catalog_users_plans_and_files(self):
        call_command('seed_demo_data', verbosity=0)

        assert Brand.objects.filter(slug='samsung').exists()
        assert Brand.objects.filter(slug='xiaomi').exists()
        assert Schematic.objects.count() >= 10
        assert SchematicFile.objects.count() >= 10
        assert User.objects.filter(phone_number='09120000000', is_superuser=True).exists()
        assert Plan.objects.filter(title='یک‌ماهه تکنسین').exists()
        assert UserSubscription.objects.has_active_subscription(
            User.objects.get(phone_number='09122222222')
        )
        assert SchematicPurchase.objects.filter(
            user__phone_number='09123333333'
        ).exists()

        # Dummy PDFs must land in protected storage, not public media.
        sample = SchematicFile.objects.first()
        assert sample.file.name.startswith('protected_schematics/')

    def test_seed_is_idempotent(self):
        call_command('seed_demo_data', verbosity=0)
        brand_count = Brand.objects.count()
        schematic_count = Schematic.objects.count()
        user_count = User.objects.count()

        call_command('seed_demo_data', verbosity=0)

        assert Brand.objects.count() == brand_count
        assert Schematic.objects.count() == schematic_count
        assert User.objects.count() == user_count

    def test_no_files_flag_skips_pdf_attachments(self):
        call_command('seed_demo_data', '--no-files', verbosity=0)
        assert Schematic.objects.exists()
        assert SchematicFile.objects.count() == 0

    def test_demo_technician_password_matches_documented_value(self):
        call_command('seed_demo_data', '--no-files', verbosity=0)
        user = User.objects.get(phone_number='09121111111')
        assert user.check_password('TechPass123!')
