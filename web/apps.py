from django.apps import AppConfig


class WebConfig(AppConfig):
    """HTML catalog and session login for technicians previewing the product in a browser."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'web'
    verbose_name = 'Web catalog'
