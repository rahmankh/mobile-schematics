"""Payment API routes."""

from django.urls import path

from .views import GuestCheckoutView, PaymentRequestView, PaymentVerifyView

app_name = 'payments'

urlpatterns = [
    path('request/', PaymentRequestView.as_view(), name='payment-request'),
    path('guest/', GuestCheckoutView.as_view(), name='guest-checkout'),
    path('verify/', PaymentVerifyView.as_view(), name='payment-verify'),
]
