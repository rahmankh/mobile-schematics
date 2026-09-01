# subscriptions/tests.py

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status
from datetime import timedelta

from .models import Plan, UserSubscription

User = get_user_model()


class SubscriptionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            phone_number="09123456789",
            password="securepassword123"
        )
        self.client.force_authenticate(user=self.user)
        self.plan = Plan.objects.create(
            title="ماهانه ویژه",
            price=200000,
            duration_days=30,
            is_active=True
        )

    def test_plan_list(self):
        response = self.client.get('/api/v1/subscriptions/plans/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_purchase_subscription(self):
        response = self.client.post('/api/v1/subscriptions/purchase/', {'plan_id': self.plan.id})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(UserSubscription.objects.filter(user=self.user, status='active').exists())

    def test_active_subscription_permission_check(self):
        UserSubscription.objects.create(
            user=self.user,
            plan=self.plan,
            start_date=timezone.now(),
            end_date=timezone.now() + timedelta(days=30),
            status='active'
        )
        response = self.client.get('/api/v1/subscriptions/my-subscription/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['has_active_subscription'])