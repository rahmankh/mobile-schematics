"""Tests for CustomUser Django admin registration and changelist access."""

from __future__ import annotations

import pytest
from django.contrib import admin
from django.urls import reverse

from accounts.admin import CustomUserAdmin
from accounts.models import CustomUser
from schematics.factories import UserFactory


@pytest.mark.django_db
class TestCustomUserAdmin:
    def test_custom_user_is_registered_with_dedicated_admin_class(self):
        assert CustomUser in admin.site._registry
        assert isinstance(admin.site._registry[CustomUser], CustomUserAdmin)

    def test_admin_uses_phone_number_instead_of_username(self):
        model_admin = admin.site._registry[CustomUser]
        flat_fields = []
        for _name, opts in model_admin.fieldsets:
            flat_fields.extend(opts['fields'])
        assert 'phone_number' in flat_fields
        assert 'username' not in flat_fields

    def test_staff_can_open_user_changelist(self, client):
        staff = UserFactory(is_staff=True, is_superuser=True, password='AdminPass123!')
        client.force_login(staff)
        url = reverse('admin:accounts_customuser_changelist')
        response = client.get(url)
        assert response.status_code == 200
        assert staff.phone_number in response.content.decode('utf-8')
