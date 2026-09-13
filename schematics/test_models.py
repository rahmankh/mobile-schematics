"""Database constraint, index, and access-matrix tests for catalog models."""

from __future__ import annotations

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.utils import timezone
from datetime import timedelta

from schematics.factories import (
    BrandFactory,
    PhoneModelFactory,
    SchematicFactory,
    SchematicFileFactory,
    SchematicPurchaseFactory,
    UserFactory,
    UserSubscriptionFactory,
)
from schematics.models import PhoneModel, Schematic, SchematicPurchase
from subscriptions.models import UserSubscription


@pytest.mark.django_db
class TestCatalogConstraints:
    def test_duplicate_phone_model_name_for_same_brand_is_rejected(self):
        brand = BrandFactory()
        PhoneModelFactory(brand=brand, name='Galaxy S24', slug='galaxy-s24')
        with pytest.raises(IntegrityError):
            PhoneModel.objects.create(
                brand=brand,
                name='Galaxy S24',
                slug='galaxy-s24-dup',
            )

    def test_same_phone_model_name_is_allowed_on_different_brands(self):
        PhoneModelFactory(name='Note 10', slug='note-10')
        other = PhoneModelFactory(name='Note 10', slug='note-10')
        assert other.pk

    def test_duplicate_schematic_title_for_same_model_and_category_is_rejected(self):
        schematic = SchematicFactory(title='Main Logic Board')
        with pytest.raises(IntegrityError):
            Schematic.objects.create(
                phone_model=schematic.phone_model,
                category=schematic.category,
                title='Main Logic Board',
            )

    def test_duplicate_purchase_for_same_user_and_schematic_is_rejected(self):
        purchase = SchematicPurchaseFactory()
        with pytest.raises(IntegrityError):
            SchematicPurchase.objects.create(
                user=purchase.user,
                schematic=purchase.schematic,
                price_paid=0,
            )

    def test_negative_schematic_price_is_rejected(self):
        with pytest.raises(IntegrityError):
            SchematicFactory(price=-1)

    def test_brand_auto_generates_unicode_slug(self):
        brand = BrandFactory(name='شیائومی', slug='')
        brand.save()
        assert brand.slug


@pytest.mark.django_db
class TestSchematicDownloadAccessMatrix:
    """Unit-test the business rules without going through HTTP."""

    def test_anonymous_never_has_access(self):
        schematic = SchematicFactory(is_free=True)
        class Anon:
            is_authenticated = False
        assert schematic.user_can_download(Anon()) is False
        assert schematic.user_can_download(None) is False

    def test_authenticated_user_can_download_free_schematic(self):
        user = UserFactory()
        schematic = SchematicFactory(is_free=True, requires_subscription=False, price=0)
        assert schematic.user_can_download(user) is True

    def test_paid_schematic_denied_without_purchase(self):
        user = UserFactory()
        schematic = SchematicFactory(is_free=False, requires_subscription=True)
        assert schematic.user_can_download(user) is False

    def test_active_subscription_does_not_grant_download(self):
        user = UserFactory()
        schematic = SchematicFactory(is_free=False, requires_subscription=True)
        UserSubscriptionFactory(user=user)
        assert schematic.user_can_download(user) is False

    def test_expired_subscription_does_not_grant_access(self):
        user = UserFactory()
        schematic = SchematicFactory(is_free=False, requires_subscription=True)
        UserSubscriptionFactory(
            user=user,
            start_date=timezone.now() - timedelta(days=60),
            end_date=timezone.now() - timedelta(days=1),
            status=UserSubscription.StatusChoices.ACTIVE,
        )
        assert schematic.user_can_download(user) is False

    def test_single_purchase_grants_access_without_subscription(self):
        user = UserFactory()
        schematic = SchematicFactory(is_free=False, requires_subscription=True)
        SchematicPurchaseFactory(user=user, schematic=schematic)
        assert schematic.user_can_download(user) is True
        assert schematic.user_can_view(user) is True

    def test_staff_can_download_paid_schematic(self):
        staff = UserFactory(is_staff=True)
        schematic = SchematicFactory(is_free=False, requires_subscription=True)
        assert schematic.user_can_download(staff) is True

    def test_subscription_never_unlocks_paid_item(self):
        user = UserFactory()
        schematic = SchematicFactory(is_free=False, requires_subscription=False)
        UserSubscriptionFactory(user=user)
        assert schematic.user_can_download(user) is False
        SchematicPurchaseFactory(user=user, schematic=schematic)
        assert schematic.user_can_download(user) is True

    def test_file_size_is_cached_on_save(self):
        schematic_file = SchematicFileFactory()
        assert schematic_file.file_size_bytes > 0

    def test_viewer_kind_follows_file_extension(self):
        pdf = SchematicFileFactory()
        assert pdf.viewer_kind == 'pdf'
        image = SchematicFileFactory(
            file=SimpleUploadedFile('board.png', b'\x89PNG\r\n\x1a\n', content_type='image/png'),
        )
        assert image.viewer_kind == 'image'
        archive = SchematicFileFactory(
            file=SimpleUploadedFile('pages.zip', b'PK\x03\x04', content_type='application/zip'),
        )
        assert archive.viewer_kind == 'other'
