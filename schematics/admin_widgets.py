"""Admin widgets that must not live inside a ModelForm Meta body."""

from __future__ import annotations

import os

from django import forms


class ProtectedAdminFileWidget(forms.ClearableFileInput):
    """
    Admin file input that never calls storage.url().

    ClearableFileInput treats an existing file as "initial" by reading
    FieldFile.url. ProtectedSchematicStorage raises there on purpose, so the
    change form would 500. Show the stored filename as plain text instead.
    """

    template_name = 'admin/schematics/widgets/protected_file_input.html'

    def is_initial(self, value):
        return bool(value) and bool(getattr(value, 'name', ''))

    def format_value(self, value):
        if self.is_initial(value):
            return os.path.basename(value.name)
        return None

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context['widget']['filename'] = self.format_value(value) or ''
        return context
