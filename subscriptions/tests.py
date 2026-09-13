# subscriptions/tests.py
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


class SubscriptionsAndAccessControlTests(APITestCase):
    def setUp(self):
        # ایجاد کاربر تستی
        self.user = User.objects.create_user(
            phone_number='09120000001',
            password='TestPassword123'
        )
        
        # ساخت دیتاهای پایه برای شماتیک
        self.brand = Brand.objects.create(name='Apple', slug='apple')
        self.phone_model = PhoneModel.objects.create(
            brand=self.brand,
            name='iPhone 13 Pro Max',
            slug='13pro-max'
        )
        self.category = SchematicCategory.objects.create(
            title='Hardware Solution',
            slug='hardware-solution'
        )
        
        # فایل فیزیکی ساختگی در حافظه
        test_file = SimpleUploadedFile(
            "board_diagram.pdf",
            b"%PDF-1.4 sample dummy content for testing",
            content_type="application/pdf"
        )
        
        # شماتیک پولی (نیازمند اشتراک)
        self.schematic = Schematic.objects.create(
            phone_model=self.phone_model,
            category=self.category,
            title='Main Logic Board Diagram',
            is_free=False,
            requires_subscription=True
        )
        self.schematic_file = SchematicFile.objects.create(
            schematic=self.schematic,
            file=test_file,
            file_title='Main Schematic File'
        )

        # پلن اشتراک آزمایشی
        self.plan = Plan.objects.create(
            title='پلن ۱ ماهه طلایی',
            price=150000,
            duration_days=30
        )
        
        self.download_url = reverse(
            'schematics:schematic-file-download',
            kwargs={'pk': self.schematic_file.pk}
        )

    def test_01_plan_creation_and_str(self):
        """تست ایجاد پلن و متد __str__"""
        self.assertIn('پلن ۱ ماهه طلایی', str(self.plan))

    def test_02_subscription_auto_end_date(self):
        """تست محاسبه خودکار end_date در صورت خالی بودن"""
        sub = UserSubscription.objects.create(
            user=self.user,
            plan=self.plan,
            start_date=timezone.now()
        )
        self.assertIsNotNone(sub.end_date)
        self.assertTrue(sub.is_valid)

    def test_03_subscription_manager_has_active(self):
        """تست کارکرد منیجر اختصاصی has_active_subscription"""
        self.assertFalse(UserSubscription.objects.has_active_subscription(self.user))
        
        UserSubscription.objects.create(
            user=self.user,
            plan=self.plan,
            start_date=timezone.now(),
            end_date=timezone.now() + timedelta(days=30),
            status=UserSubscription.StatusChoices.ACTIVE
        )
        self.assertTrue(UserSubscription.objects.has_active_subscription(self.user))

    def test_04_download_file_permission_denied_without_subscription(self):
        """کاربر بدون اشتراک فعال باید پاسخ 403 دریافت کند"""
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.download_url)
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("خرید", str(response.data.get('detail', '')))

    def test_05_download_file_permission_denied_with_active_subscription(self):
        """Active subscriptions no longer unlock paid files."""
        UserSubscription.objects.create(
            user=self.user,
            plan=self.plan,
            start_date=timezone.now(),
            end_date=timezone.now() + timedelta(days=30),
            status=UserSubscription.StatusChoices.ACTIVE
        )
        
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.download_url)
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)