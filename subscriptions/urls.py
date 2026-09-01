# subscriptions/urls.py

from django.urls import path
from .views import PlanListAPIView, CurrentUserSubscriptionAPIView, PurchaseSubscriptionAPIView

app_name = 'subscriptions'

urlpatterns = [
    path('plans/', PlanListAPIView.as_view(), name='plan-list'),
    path('my-subscription/', CurrentUserSubscriptionAPIView.as_view(), name='my-subscription'),
    path('purchase/', PurchaseSubscriptionAPIView.as_view(), name='purchase-subscription'),
]