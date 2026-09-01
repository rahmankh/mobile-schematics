# subscriptions/tests.py

from datetime import timedelta
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from schematics.models import Brand, PhoneModel, SchematicCategory, Schematic, SchematicFile
from subscriptions.models import Plan, UserSubscription

User = get_user_model()


class SubscriptionsAndAccessControlTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        # ساخت کاربر عادی
        self.user = User.objects.create_user(
            phone_number="09121112233",
            password="testpassword123",
            first_name="Rahman",
            last_name="Tech"
        )

        # ساخت کاربر ادمین / Staff
        self.staff_user = User.objects.create_user(
            phone_number="09129998877",
            password="adminpassword123",
            is_staff=True
        )

        # ساخت پلن فعال
        self.plan = Plan.objects.create(
            title="پلن ۳۰ روزه طلایی",
            description="دسترسی کامل به تمام شماتیک‌ها",
            price=150000,
            duration_days=30,
            is_active=True
        )

        # ساخت دیتای نمونه شماتیک
        self.brand = Brand.objects.create(name="Samsung", slug="samsung")
        self.phone_model = PhoneModel.objects.create(
            brand=self.brand,
            name="Galaxy S23",
            slug="galaxy-s23",
            technical_code="SM-S911B"
        )
        self.category = SchematicCategory.objects.create(
            title="شماتیک کامل",
            slug="schematic-full"
        )
        self.schematic = Schematic.objects.create(
            phone_model=self.phone_model,
            category=self.category,
            title="Samsung Galaxy S23 Board Schematic"
        )

        # ایجاد فایل نمونه منطبق بر فیلدهای مدل
        sample_pdf = SimpleUploadedFile("schematic.pdf", b"dummy pdf content", content_type="application/pdf")
        self.schematic_file = SchematicFile.objects.create(
            schematic=self.schematic,
            file=sample_pdf
        )

    # تست ۱: بررسی لود صحیح صفحه خانگی داشبورد
    def test_01_home_page_loads_successfully(self):
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTemplateUsed(response, 'home.html')

    # تست ۲: مشاهده لیست پلن‌های فعال
    def test_02_plan_list_endpoint(self):
        url = reverse('subscriptions:plan-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['title'], "پلن ۳۰ روزه طلایی")

    # تست ۳: خرید و فعال‌سازی اشتراک
    def test_03_purchase_subscription_success(self):
        self.client.force_authenticate(user=self.user)
        url = reverse('subscriptions:purchase-subscription')
        payload = {'plan_id': self.plan.id}

        response = self.client.post(url, data=payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(UserSubscription.objects.filter(user=self.user, status='active').exists())

        # بررسی وضعیت اشتراک جاری
        sub_status_url = reverse('subscriptions:my-subscription')
        sub_response = self.client.get(sub_status_url)
        self.assertEqual(sub_response.status_code, status.HTTP_200_OK)
        self.assertTrue(sub_response.data['has_active_subscription'])

    # تست ۴: مسدود شدن دسترسی به دانلود فایل برای کاربر بدون اشتراک (403 Forbidden)
    def test_04_download_file_permission_denied_without_subscription(self):
        self.client.force_authenticate(user=self.user)
        download_url = reverse('schematics:schematic-file-download', kwargs={'pk': self.schematic_file.pk})

        response = self.client.get(download_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("برای دسترسی و دانلود این فایل، نیاز به تهیه یا تمدید اشتراک فعال دارید.", str(response.data))

    # تست ۵: دسترسی موفق به دانلود فایل با داشتن اشتراک معتبر (200 OK)
    def test_05_download_file_permission_granted_with_active_subscription(self):
        self.client.force_authenticate(user=self.user)
        
        # ثبت اشتراک فعال برای کاربر
        UserSubscription.objects.create(
            user=self.user,
            plan=self.plan,
            start_date=timezone.now(),
            end_date=timezone.now() + timedelta(days=30),
            status='active'
        )

        download_url = reverse('schematics:schematic-file-download', kwargs={'pk': self.schematic_file.pk})
        response = self.client.get(download_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], self.schematic_file.id)
        self.assertIn('file', response.data)

    # تست ۶: دسترسی بدون محدودیت ادمین/Staff به فایل
    def test_06_download_file_allowed_for_staff_without_subscription(self):
        self.client.force_authenticate(user=self.staff_user)
        download_url = reverse('schematics:schematic-file-download', kwargs={'pk': self.schematic_file.pk})

        response = self.client.get(download_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)