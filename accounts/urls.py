from django.urls import path
from .views import (
    CustomLoginView,
    CustomTokenRefreshView,
    ProfileView,
    RegisterView,
    SetPasswordView,
)

app_name = 'accounts'

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', CustomLoginView.as_view(), name='login'),
    path('token/refresh/', CustomTokenRefreshView.as_view(), name='token_refresh'),
    path('profile/', ProfileView.as_view(), name='profile'),
    path('set-password/', SetPasswordView.as_view(), name='set-password'),
]
