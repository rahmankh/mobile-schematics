from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class PaymentsConfig(AppConfig):
    """Checkout and gateway verification for subscriptions and single schematics."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'payments'
    verbose_name = _('Payments')

    def ready(self):
        # Second line of defence: a mis-set DEBUG after import still cannot serve mock money.
        from config.security import enforce_fail_closed_from_django_settings

        enforce_fail_closed_from_django_settings()
