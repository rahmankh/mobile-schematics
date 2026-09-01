
from rest_framework.permissions import BasePermission
from django.utils import timezone
from .models import UserSubscription


class HasActiveSubscription(BasePermission):
    """
    بررسی می‌کند که آیا کاربر احراز هویت شده دارای اشتراک فعال و معتبر است یا خیر.
    کاربران superuser و staff به صورت پیش‌فرض دسترسی دارند.
    """
    message = "برای دسترسی و دانلود این فایل، نیاز به تهیه یا تمدید اشتراک فعال دارید."

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False

        if request.user.is_staff or request.user.is_superuser:
            return True

        return UserSubscription.objects.filter(
            user=request.user,
            status='active',
            end_date__gt=timezone.now()
        ).exists()