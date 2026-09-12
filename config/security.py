"""
Fail-closed production guards.

Called at the end of settings load and from PaymentsConfig.ready(). Pytest is
skipped so the suite can keep SQLite + MockGateway; gunicorn/runserver with
DEBUG=False must not boot on the insecure defaults.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

# Must stay in sync with the SECRET_KEY default in settings.py Env().
DEFAULT_INSECURE_SECRET_KEY = 'django-insecure-dev-only-change-me'

_INSECURE_SECRET_MARKERS = (
    'insecure',
    'change-me',
    'changeme',
    'django-insecure',
)

_SQLITE_ENGINE_MARKERS = (
    'sqlite3',
    'django.db.backends.sqlite3',
)


def running_under_pytest() -> bool:
    """True when this process is a pytest or Django test runner invocation."""
    if os.environ.get('PYTEST_CURRENT_TEST'):
        return True
    argv0 = Path(sys.argv[0]).name.lower() if sys.argv else ''
    if 'pytest' in argv0 or argv0 in {'py.test', 'py.test.exe', 'pytest.exe'}:
        return True
    if 'pytest' in sys.modules:
        return True
    if len(sys.argv) >= 2 and sys.argv[1] == 'test':
        return True
    return False


def is_insecure_secret_key(secret_key: str | None) -> bool:
    """Empty, too short, or still the documented Django/dev placeholder."""
    if secret_key is None:
        return True
    key = str(secret_key).strip()
    if not key:
        return True
    if len(key) < 32:
        return True
    lowered = key.lower()
    if lowered == DEFAULT_INSECURE_SECRET_KEY:
        return True
    return any(marker in lowered for marker in _INSECURE_SECRET_MARKERS)


def is_sqlite_engine(engine: str | None) -> bool:
    name = (engine or '').lower()
    return any(marker in name for marker in _SQLITE_ENGINE_MARKERS)


def mock_gateway_allowed(*, debug: bool) -> bool:
    """Mock PSP is only legal in DEBUG or under the test runner."""
    return bool(debug) or running_under_pytest()


def validate_runtime_settings(
    *,
    debug: bool,
    secret_key: str | None,
    payment_gateway: str | None,
    database_engine: str | None,
    django_env: str = 'development',
) -> None:
    """
    Raise ImproperlyConfigured when this process looks like production and is
    still using placeholder secrets, the mock gateway, or SQLite.
    """
    env_name = (django_env or 'development').strip().lower()
    production_shaped = (not debug) or env_name == 'production'
    if not production_shaped:
        return

    if is_insecure_secret_key(secret_key):
        raise ImproperlyConfigured(
            'DEBUG=False/production cannot boot with an empty, short, or '
            'placeholder SECRET_KEY. Set a unique value of at least 32 characters '
            'that does not contain "insecure" or "change-me".'
        )

    gateway = (payment_gateway or '').strip().lower()
    if gateway == 'mock':
        raise ImproperlyConfigured(
            'PAYMENT_GATEWAY=mock is not allowed when DEBUG=False or '
            'DJANGO_ENV=production. Point PAYMENT_GATEWAY at a live adapter '
            '(zarinpal/idpay) or keep DEBUG=True for local work.'
        )

    if is_sqlite_engine(database_engine):
        raise ImproperlyConfigured(
            'SQLite is not allowed when DEBUG=False or DJANGO_ENV=production. '
            'Set DATABASE_URL to PostgreSQL (or another production engine).'
        )


def maybe_enforce_fail_closed(
    *,
    debug: bool,
    secret_key: str | None,
    payment_gateway: str | None,
    database_engine: str | None,
    django_env: str = 'development',
) -> None:
    """Settings-load hook. No-op under pytest so the suite can use dev defaults."""
    if running_under_pytest():
        return
    validate_runtime_settings(
        debug=debug,
        secret_key=secret_key,
        payment_gateway=payment_gateway,
        database_engine=database_engine,
        django_env=django_env,
    )


def enforce_fail_closed_from_django_settings() -> None:
    """AppConfig.ready() hook. Reads live django.conf.settings."""
    if running_under_pytest():
        return
    from django.conf import settings as django_settings

    engine = django_settings.DATABASES['default']['ENGINE']
    validate_runtime_settings(
        debug=django_settings.DEBUG,
        secret_key=django_settings.SECRET_KEY,
        payment_gateway=getattr(django_settings, 'PAYMENT_GATEWAY', 'mock'),
        database_engine=engine,
        django_env=getattr(django_settings, 'DJANGO_ENV', 'development'),
    )
