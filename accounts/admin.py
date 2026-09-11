"""
Django admin for technician accounts.

CustomUser uses `phone_number` as USERNAME_FIELD (no `username` column),
so UserAdmin fieldsets must be fully overridden — the stock ones reference
`username` and would crash the change form.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from django.utils.translation import gettext_lazy as _

from .models import CustomUser


class CustomUserCreationForm(UserCreationForm):
    """Add-user form bound to CustomUser. Password widgets come from UserCreationForm."""

    class Meta(UserCreationForm.Meta):
        model = CustomUser
        fields = ('phone_number', 'first_name', 'last_name', 'repair_shop_name', 'role')


class CustomUserChangeForm(UserChangeForm):
    """Change-user form bound to CustomUser (phone login, no username)."""

    class Meta(UserChangeForm.Meta):
        model = CustomUser
        fields = '__all__'


@admin.register(CustomUser)
class CustomUserAdmin(BaseUserAdmin):
    """
    Staff UI for technicians and admins.

    `list_display` / `search_fields` are phone-centric because that is the
    login identifier technicians actually know.
    """

    form = CustomUserChangeForm
    add_form = CustomUserCreationForm
    model = CustomUser
    ordering = ('phone_number',)
    list_display = (
        'phone_number',
        'first_name',
        'last_name',
        'repair_shop_name',
        'role',
        'is_staff',
        'is_active',
        'date_joined',
    )
    list_filter = ('role', 'is_staff', 'is_superuser', 'is_active')
    search_fields = ('phone_number', 'first_name', 'last_name', 'repair_shop_name')
    readonly_fields = ('date_joined', 'last_login')
    filter_horizontal = ('groups', 'user_permissions')

    fieldsets = (
        (None, {'fields': ('phone_number', 'password')}),
        (
            _('Personal info'),
            {'fields': ('first_name', 'last_name', 'repair_shop_name', 'role')},
        ),
        (
            _('Permissions'),
            {
                'fields': (
                    'is_active',
                    'is_staff',
                    'is_superuser',
                    'groups',
                    'user_permissions',
                )
            },
        ),
        (_('Important dates'), {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (
            None,
            {
                'classes': ('wide',),
                'fields': (
                    'phone_number',
                    'first_name',
                    'last_name',
                    'repair_shop_name',
                    'role',
                    'password1',
                    'password2',
                    'is_staff',
                    'is_superuser',
                ),
            },
        ),
    )
