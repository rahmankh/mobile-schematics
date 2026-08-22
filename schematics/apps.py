from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class SchematicsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'schematics'
    verbose_name = _('Schematics Management')