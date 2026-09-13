from datetime import timedelta
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from schematics.models import Brand, PhoneModel, SchematicCategory, Schematic, SchematicFile
from subscriptions.models import Plan, UserSubscription

User = get_user_model()


class SchematicDownloadPermissionTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(phone_number='09120000001', password='Password123')
        self.brand = Brand.objects.create(name='Apple', slug='apple')
        self.phone_model = PhoneModel.objects.create(brand=self.brand, name='iPhone 13 Pro Max', slug='13pro-max')
        self.category = SchematicCategory.objects.create(title='Hardware Solution', slug='hardware-solution')

        # فایل تستی
        test_file = SimpleUploadedFile("board.pdf", b"%PDF-1.4 test content", content_type="application/pdf")

        # شماتیک پولی
        self.paid_schematic = Schematic.objects.create(
            phone_model=self.phone_model,
            category=self.category,
            title='Paid Board Schematic',
            is_free=False,
            requires_subscription=True
        )
        self.paid_file = SchematicFile.objects.create(
            schematic=self.paid_schematic,
            file=test_file,
            file_title='Main Logic Board'
        )

        self.download_url = reverse('schematics:schematic-file-download', kwargs={'pk': self.paid_file.pk})

    def test_anonymous_user_cannot_download(self):
        """کاربر بدون احراز هویت باید 401 یا 403 دریافت کند"""
        response = self.client.get(self.download_url)
        self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

    def test_user_without_purchase_forbidden(self):
        """Logged-in users still need a single purchase (or a free schematic)."""
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.download_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_user_with_active_subscription_cannot_download(self):
        """Subscriptions no longer unlock paid files."""
        plan = Plan.objects.create(title='Monthly Plan', price=100000, duration_days=30)
        UserSubscription.objects.create(
            user=self.user,
            plan=plan,
            start_date=timezone.now(),
            end_date=timezone.now() + timedelta(days=30),
            status=UserSubscription.StatusChoices.ACTIVE
        )

        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.download_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)