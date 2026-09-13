"""Browser routes for the technician catalog UI (not the JSON API)."""

from django.urls import path

from .views import (
    BrandDetailView,
    CartAddView,
    CartCheckoutView,
    CartPageView,
    CartRemoveView,
    HomeView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    PaymentCallbackView,
    PhoneModelDetailView,
    ProfilePageView,
    SchematicCheckoutView,
    SchematicDetailPageView,
    TechnicianLoginView,
    TechnicianLogoutView,
    TechnicianRegisterView,
    WalletPaySchematicView,
    WalletTopUpView,
)

app_name = 'web'

urlpatterns = [
    path('', HomeView.as_view(), name='home'),
    path('login/', TechnicianLoginView.as_view(), name='login'),
    path('register/', TechnicianRegisterView.as_view(), name='register'),
    path('password-reset/', PasswordResetRequestView.as_view(), name='password-reset'),
    path(
        'password-reset/confirm/',
        PasswordResetConfirmView.as_view(),
        name='password-reset-confirm',
    ),
    path('logout/', TechnicianLogoutView.as_view(), name='logout'),
    path('profile/', ProfilePageView.as_view(), name='profile'),
    path('cart/', CartPageView.as_view(), name='cart'),
    path('cart/checkout/', CartCheckoutView.as_view(), name='cart-checkout'),
    path('cart/<int:pk>/remove/', CartRemoveView.as_view(), name='cart-remove'),
    path('schematics/<int:pk>/cart/', CartAddView.as_view(), name='cart-add'),
    path('wallet/topup/', WalletTopUpView.as_view(), name='wallet-topup'),
    path('payments/callback/', PaymentCallbackView.as_view(), name='payment-callback'),
    path(
        'schematics/<int:pk>/checkout/',
        SchematicCheckoutView.as_view(),
        name='schematic-checkout',
    ),
    path(
        'schematics/<int:pk>/wallet-pay/',
        WalletPaySchematicView.as_view(),
        name='wallet-pay-schematic',
    ),
    path('brands/<slug:slug>/', BrandDetailView.as_view(), name='brand-detail'),
    path(
        'brands/<slug:brand_slug>/<slug:model_slug>/',
        PhoneModelDetailView.as_view(),
        name='model-detail',
    ),
    path('schematics/<int:pk>/', SchematicDetailPageView.as_view(), name='schematic-detail'),
]
