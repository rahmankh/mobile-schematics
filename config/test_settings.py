"""Regression tests for environment-driven Django settings."""

from __future__ import annotations

from pathlib import Path

from django.conf import settings


def test_secret_key_is_not_the_old_hardcoded_insecure_value():
    """The key that previously lived in settings.py must never return."""
    assert settings.SECRET_KEY
    assert 'a-=vg0#-eprh#5-%j^*=wjkq!4c_q^u@r8x-i+on$a=ks=19jq' not in settings.SECRET_KEY


def test_settings_module_loads_values_through_django_environ():
    source = (Path(settings.BASE_DIR) / 'config' / 'settings.py').read_text(encoding='utf-8')
    assert 'environ.Env' in source
    assert 'env.db(' in source
    assert 'ALLOWED_HOSTS' in source


def test_protected_media_root_is_distinct_from_public_media_root():
    assert Path(settings.PROTECTED_MEDIA_ROOT).resolve() != Path(settings.MEDIA_ROOT).resolve()


def test_allowed_hosts_is_a_list():
    assert isinstance(settings.ALLOWED_HOSTS, list)
    assert len(settings.ALLOWED_HOSTS) >= 1


def test_database_engine_is_configured():
    engine = settings.DATABASES['default']['ENGINE']
    assert 'sqlite3' in engine or 'postgresql' in engine


def test_simple_jwt_rotation_and_blacklist_are_enabled():
    jwt = settings.SIMPLE_JWT
    assert jwt['ROTATE_REFRESH_TOKENS'] is True
    assert jwt['BLACKLIST_AFTER_ROTATION'] is True
    assert 'rest_framework_simplejwt.token_blacklist' in settings.INSTALLED_APPS


def test_env_example_documents_required_production_keys():
    example = (Path(settings.BASE_DIR) / '.env.example').read_text(encoding='utf-8')
    for key in ('SECRET_KEY', 'DEBUG', 'ALLOWED_HOSTS', 'DATABASE_URL', 'DJANGO_ENV', 'PAYMENT_GATEWAY'):
        assert key in example
