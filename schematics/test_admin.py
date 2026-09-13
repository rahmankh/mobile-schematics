"""Django admin: publish a schematic (model, file, price) on one page."""

from __future__ import annotations

import os

import pytest
from django.contrib import admin
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from schematics.admin import SchematicAdmin, SchematicFileInline, SchematicFileInlineForm
from schematics.admin_widgets import ProtectedAdminFileWidget
from schematics.factories import (
    MINIMAL_PDF_BYTES,
    PhoneModelFactory,
    SchematicCategoryFactory,
    SchematicFileFactory,
    UserFactory,
)
from schematics.models import Schematic, SchematicFile


def _staff_client(client):
    staff = UserFactory(is_staff=True, is_superuser=True, password='AdminPass123!')
    client.force_login(staff)
    return staff


def _inline_payload(file_title='Board PDF', upload=None):
    payload = {
        'files-TOTAL_FORMS': '1',
        'files-INITIAL_FORMS': '0',
        'files-MIN_NUM_FORMS': '1',
        'files-MAX_NUM_FORMS': '5',
        'files-0-id': '',
        'files-0-schematic': '',
        'files-0-file_title': file_title,
    }
    if upload is not None:
        payload['files-0-file'] = upload
    return payload


@pytest.mark.django_db
class TestSchematicAdminForm:
    def test_admin_module_loads_widget_without_nameerror(self):
        assert SchematicFileInlineForm.Meta.widgets['file'] is ProtectedAdminFileWidget
        form = SchematicFileInlineForm()
        assert isinstance(form.fields['file'].widget, ProtectedAdminFileWidget)

    def test_schematic_file_is_not_a_standalone_admin_model(self):
        assert SchematicFile not in admin.site._registry
        model_admin = admin.site._registry[Schematic]
        assert isinstance(model_admin, SchematicAdmin)
        assert SchematicFileInline in model_admin.inlines

    def test_create_form_keeps_essentials_and_hides_clutter(self):
        model_admin = admin.site._registry[Schematic]
        declared = []
        for _name, opts in model_admin.fieldsets:
            declared.extend(opts['fields'])
        assert declared == [
            'phone_model',
            'category',
            'title',
            'is_free',
            'price',
            'description',
        ]
        assert 'requires_subscription' not in declared
        assert 'view_count' not in declared
        assert 'created_at' not in declared
        assert 'requires_subscription' not in model_admin.list_display
        assert 'requires_subscription' not in model_admin.list_filter

    def test_add_page_is_rtl_and_shows_inline_upload(self, client):
        _staff_client(client)
        PhoneModelFactory()
        SchematicCategoryFactory()
        response = client.get(reverse('admin:schematics_schematic_add'))
        html = response.content.decode('utf-8')

        assert response.status_code == 200
        assert 'dir="rtl"' in html
        assert 'name="price"' in html
        assert 'name="is_free"' in html
        assert 'name="phone_model"' in html
        assert 'name="files-0-file"' in html
        assert 'name="requires_subscription"' not in html
        assert 'name="view_count"' not in html
        assert 'آپلود فایل' in html
        assert 'قیمت' in html

    def test_staff_creates_schematic_with_file_and_price_in_one_post(self, client):
        _staff_client(client)
        phone = PhoneModelFactory()
        category = SchematicCategoryFactory()
        upload = SimpleUploadedFile(
            'board.pdf',
            MINIMAL_PDF_BYTES,
            content_type='application/pdf',
        )

        response = client.post(
            reverse('admin:schematics_schematic_add'),
            {
                'phone_model': phone.pk,
                'category': category.pk,
                'title': 'Main Logic Board',
                'price': '150000',
                'description': '',
                **_inline_payload(file_title='', upload=upload),
            },
        )

        assert response.status_code == 302
        schematic = Schematic.objects.get(title='Main Logic Board')
        assert schematic.phone_model_id == phone.pk
        assert schematic.price == 150000
        assert schematic.is_free is False
        attached = schematic.files.get()
        assert attached.file_title == 'board.pdf'
        assert attached.file_size_bytes > 0
        assert 'protected_schematics/' in attached.file.name.replace('\\', '/')

    def test_free_schematic_forces_zero_price(self, client):
        _staff_client(client)
        phone = PhoneModelFactory()
        category = SchematicCategoryFactory()
        upload = SimpleUploadedFile(
            'free.pdf',
            MINIMAL_PDF_BYTES,
            content_type='application/pdf',
        )

        response = client.post(
            reverse('admin:schematics_schematic_add'),
            {
                'phone_model': phone.pk,
                'category': category.pk,
                'title': 'Free Board',
                'is_free': 'on',
                'price': '99000',
                **_inline_payload(upload=upload),
            },
        )

        assert response.status_code == 302
        schematic = Schematic.objects.get(title='Free Board')
        assert schematic.is_free is True
        assert schematic.price == 0

    def test_paid_schematic_rejects_zero_price(self, client):
        _staff_client(client)
        phone = PhoneModelFactory()
        category = SchematicCategoryFactory()
        upload = SimpleUploadedFile(
            'paid.pdf',
            MINIMAL_PDF_BYTES,
            content_type='application/pdf',
        )

        response = client.post(
            reverse('admin:schematics_schematic_add'),
            {
                'phone_model': phone.pk,
                'category': category.pk,
                'title': 'Paid Board',
                'price': '0',
                **_inline_payload(upload=upload),
            },
        )

        assert response.status_code == 200
        html = response.content.decode('utf-8')
        assert 'برای نقشه پولی، قیمت باید بزرگ‌تر از صفر باشد.' in html
        assert not Schematic.objects.filter(title='Paid Board').exists()

    def test_create_without_file_is_rejected(self, client):
        _staff_client(client)
        phone = PhoneModelFactory()
        category = SchematicCategoryFactory()

        response = client.post(
            reverse('admin:schematics_schematic_add'),
            {
                'phone_model': phone.pk,
                'category': category.pk,
                'title': 'Missing File',
                'price': '120000',
                **_inline_payload(),
            },
        )

        assert response.status_code == 200
        assert not Schematic.objects.filter(title='Missing File').exists()

    def test_change_page_keeps_file_inline(self, client):
        _staff_client(client)
        schematic_file = SchematicFileFactory()
        url = reverse('admin:schematics_schematic_change', args=[schematic_file.schematic.pk])
        html = client.get(url).content.decode('utf-8')
        assert 'name="price"' in html
        assert 'name="files-0-file"' in html
        assert 'name="requires_subscription"' not in html
        assert 'protected-filename' in html
        assert os.path.basename(schematic_file.file.name) in html
