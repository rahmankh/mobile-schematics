from django.test import TestCase

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

User = get_user_model()


class AccountsAPITests(APITestCase):
    def setUp(self):
        self.register_url = reverse('accounts:register')
        self.login_url = reverse('accounts:login')
        self.profile_url = reverse('accounts:profile')
        
        self.valid_user_data = {
            'phone_number': '09123456789',
            'first_name': 'Ali',
            'last_name': 'Ahmadi',
            'repair_shop_name': 'Tehran Repair',
            'password': 'StrongPassword@123',
            'password_confirm': 'StrongPassword@123',
        }

    def test_user_registration_success(self):
        """تست ثبت‌نام موفق تکنسین جدید"""
        response = self.client.post(self.register_url, self.valid_user_data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(User.objects.filter(phone_number='09123456789').exists())

    def test_registration_invalid_phone_number(self):
        """تست رد کردن شماره موبایل با فرمت اشتباه"""
        data = self.valid_user_data.copy()
        data['phone_number'] = '12345'
        response = self.client.post(self.register_url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_registration_password_mismatch(self):
        """تست عدم تطابق تکرار رمز عبور"""
        data = self.valid_user_data.copy()
        data['password_confirm'] = 'DifferentPassword@123'
        response = self.client.post(self.register_url, data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_user_jwt_login_success(self):
        """تست ورود و دریافت توکن‌های JWT"""
        User.objects.create_user(
            phone_number='09123456789',
            password='StrongPassword@123',
            first_name='Ali'
        )
        login_data = {
            'phone_number': '09123456789',
            'password': 'StrongPassword@123',
        }
        response = self.client.post(self.login_url, login_data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)
        self.assertIn('user', response.data)

    def test_profile_access_with_jwt_token(self):
        """تست دسترسی به اندپوینت پروفایل با هدر Authorization"""
        user = User.objects.create_user(
            phone_number='09123456789',
            password='StrongPassword@123',
            first_name='Ali',
            repair_shop_name='Tehran Repair'
        )
        # لاگین جهت دریافت توکن
        login_res = self.client.post(self.login_url, {
            'phone_number': '09123456789',
            'password': 'StrongPassword@123'
        })
        token = login_res.data['access']

        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        response = self.client.get(self.profile_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['phone_number'], '09123456789')
        self.assertEqual(response.data['repair_shop_name'], 'Tehran Repair')