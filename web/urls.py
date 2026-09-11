"""Browser routes for the technician catalog UI (not the JSON API)."""

from django.urls import path

from .views import (
    BrandDetailView,
    HomeView,
    PhoneModelDetailView,
    ProfilePageView,
    SchematicDetailPageView,
    TechnicianLoginView,
    TechnicianLogoutView,
)

app_name = 'web'

urlpatterns = [
    path('', HomeView.as_view(), name='home'),
    path('login/', TechnicianLoginView.as_view(), name='login'),
    path('logout/', TechnicianLogoutView.as_view(), name='logout'),
    path('profile/', ProfilePageView.as_view(), name='profile'),
    path('brands/<slug:slug>/', BrandDetailView.as_view(), name='brand-detail'),
    path(
        'brands/<slug:brand_slug>/<slug:model_slug>/',
        PhoneModelDetailView.as_view(),
        name='model-detail',
    ),
    path('schematics/<int:pk>/', SchematicDetailPageView.as_view(), name='schematic-detail'),
]
