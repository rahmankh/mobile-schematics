"""DRF permission classes for subscription-gated views."""

from rest_framework.permissions import BasePermission

from .models import UserSubscription


class HasActiveSubscription(BasePermission):
    """
    Allow access when the request user currently has a valid subscription.

    Staff and superusers bypass the check so support can preview paid files.
    The actual existence query is `UserSubscriptionManager.has_active_subscription`,
    which uses the (user, status, end_date) index.
    """

    message = 'برای دسترسی و دانلود این فایل، نیاز به تهیه یا تمدید اشتراک فعال دارید.'

    def has_permission(self, request, view) -> bool:
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if user.is_staff or user.is_superuser:
            return True
        return UserSubscription.objects.has_active_subscription(user)
