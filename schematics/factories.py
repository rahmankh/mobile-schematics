"""
Test factories for accounts, catalog, files, and subscriptions.

Factories keep API tests free of 20-line setUp blocks and are reused by the
seed command's expectations (Iranian phone numbers, PDF-like payloads).
"""

from __future__ import annotations

import factory
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
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

# Minimal PDF header so viewers/tests treat the payload as application/pdf.
MINIMAL_PDF_BYTES = b'%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n'


class UserFactory(factory.django.DjangoModelFactory):
    """Technician account. Phone numbers stay within the 09xxxxxxxxx shape used at login."""

    class Meta:
        model = User
        skip_postgeneration_save = True

    phone_number = factory.Sequence(lambda n: f'0912{n:07d}')
    first_name = factory.Sequence(lambda n: f'Tech{n}')
    last_name = 'Tester'
    repair_shop_name = factory.Sequence(lambda n: f'Repair Shop {n}')
    role = User.RoleChoices.TECHNICIAN
    is_active = True

    @factory.post_generation
    def password(obj, create, extracted, **kwargs):
        raw = extracted or 'Password123!'
        obj.set_password(raw)
        if create:
            obj.save(update_fields=['password'])


class BrandFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Brand

    name = factory.Sequence(lambda n: f'Brand {n}')
    slug = factory.Sequence(lambda n: f'brand-{n}')


class PhoneModelFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PhoneModel

    brand = factory.SubFactory(BrandFactory)
    name = factory.Sequence(lambda n: f'Model {n}')
    slug = factory.Sequence(lambda n: f'model-{n}')
    technical_code = factory.Sequence(lambda n: f'SM-TEST{n:03d}')


class SchematicCategoryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SchematicCategory

    title = factory.Sequence(lambda n: f'Category {n}')
    slug = factory.Sequence(lambda n: f'category-{n}')
    description = 'Repair category for tests'


class SchematicFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Schematic

    phone_model = factory.SubFactory(PhoneModelFactory)
    category = factory.SubFactory(SchematicCategoryFactory)
    title = factory.Sequence(lambda n: f'Schematic {n}')
    description = 'Voltage rails and IC map for tests.'
    is_free = False
    price = 150000
    requires_subscription = True


class SchematicFileFactory(factory.django.DjangoModelFactory):
    """Uploads a tiny PDF into ProtectedSchematicStorage (not MEDIA_ROOT)."""

    class Meta:
        model = SchematicFile

    schematic = factory.SubFactory(SchematicFactory)
    file_title = 'Main Board PDF'
    file = factory.LazyFunction(
        lambda: SimpleUploadedFile('board.pdf', MINIMAL_PDF_BYTES, content_type='application/pdf')
    )


class SchematicPurchaseFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SchematicPurchase

    user = factory.SubFactory(UserFactory)
    schematic = factory.SubFactory(SchematicFactory)
    price_paid = 150000


class PlanFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Plan

    title = factory.Sequence(lambda n: f'Plan {n}')
    description = 'Test subscription plan'
    price = 250000
    duration_days = 30
    is_active = True


class UserSubscriptionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = UserSubscription

    user = factory.SubFactory(UserFactory)
    plan = factory.SubFactory(PlanFactory)
    start_date = factory.LazyFunction(timezone.now)
    status = UserSubscription.StatusChoices.ACTIVE

    @factory.lazy_attribute
    def end_date(self):
        from datetime import timedelta

        return self.start_date + timedelta(days=self.plan.duration_days)
