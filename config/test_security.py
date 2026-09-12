"""Fail-closed production boot: insecure secrets, mock gateway, and SQLite."""

from __future__ import annotations

from pathlib import Path

import pytest
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from config.security import (
    DEFAULT_INSECURE_SECRET_KEY,
    maybe_enforce_fail_closed,
    mock_gateway_allowed,
    running_under_pytest,
    validate_runtime_settings,
)
from payments.gateways import MockGateway, get_gateway

SECURE_SECRET = 'prod-secret-key-value-that-is-long-enough-32'
POSTGRES = 'django.db.backends.postgresql'
SQLITE = 'django.db.backends.sqlite3'


def test_pytest_process_is_detected_as_test_runtime():
    assert running_under_pytest() is True


def test_debug_true_allows_dev_placeholders():
    validate_runtime_settings(
        debug=True,
        secret_key=DEFAULT_INSECURE_SECRET_KEY,
        payment_gateway='mock',
        database_engine=SQLITE,
        django_env='development',
    )


def test_debug_false_insecure_default_secret_refuses_boot():
    with pytest.raises(ImproperlyConfigured, match='SECRET_KEY'):
        validate_runtime_settings(
            debug=False,
            secret_key=DEFAULT_INSECURE_SECRET_KEY,
            payment_gateway='zarinpal',
            database_engine=POSTGRES,
        )


@pytest.mark.parametrize('secret', ['', '   ', None, 'short', 'django-insecure-local'])
def test_debug_false_empty_or_placeholder_secret_refuses_boot(secret):
    with pytest.raises(ImproperlyConfigured, match='SECRET_KEY'):
        validate_runtime_settings(
            debug=False,
            secret_key=secret,
            payment_gateway='zarinpal',
            database_engine=POSTGRES,
        )


def test_debug_false_mock_gateway_refuses_boot():
    with pytest.raises(ImproperlyConfigured, match='PAYMENT_GATEWAY'):
        validate_runtime_settings(
            debug=False,
            secret_key=SECURE_SECRET,
            payment_gateway='mock',
            database_engine=POSTGRES,
        )


def test_debug_false_sqlite_refuses_boot():
    with pytest.raises(ImproperlyConfigured, match='SQLite'):
        validate_runtime_settings(
            debug=False,
            secret_key=SECURE_SECRET,
            payment_gateway='zarinpal',
            database_engine=SQLITE,
        )


def test_django_env_production_refuses_sqlite_even_when_debug_true():
    with pytest.raises(ImproperlyConfigured, match='SQLite'):
        validate_runtime_settings(
            debug=True,
            secret_key=SECURE_SECRET,
            payment_gateway='zarinpal',
            database_engine=SQLITE,
            django_env='production',
        )


def test_django_env_production_refuses_mock_and_insecure_secret():
    with pytest.raises(ImproperlyConfigured, match='SECRET_KEY'):
        validate_runtime_settings(
            debug=True,
            secret_key=DEFAULT_INSECURE_SECRET_KEY,
            payment_gateway='zarinpal',
            database_engine=POSTGRES,
            django_env='production',
        )
    with pytest.raises(ImproperlyConfigured, match='PAYMENT_GATEWAY'):
        validate_runtime_settings(
            debug=True,
            secret_key=SECURE_SECRET,
            payment_gateway='mock',
            database_engine=POSTGRES,
            django_env='production',
        )


def test_debug_false_with_hardened_values_is_allowed():
    validate_runtime_settings(
        debug=False,
        secret_key=SECURE_SECRET,
        payment_gateway='zarinpal',
        database_engine=POSTGRES,
        django_env='production',
    )


def test_maybe_enforce_is_a_noop_under_pytest():
    """The running test process must still boot; enforcement uses validate_* directly."""
    maybe_enforce_fail_closed(
        debug=False,
        secret_key=DEFAULT_INSECURE_SECRET_KEY,
        payment_gateway='mock',
        database_engine=SQLITE,
        django_env='production',
    )


def test_settings_module_wires_fail_closed_hook():
    source = (Path(settings.BASE_DIR) / 'config' / 'settings.py').read_text(encoding='utf-8')
    assert 'maybe_enforce_fail_closed' in source
    assert 'DJANGO_ENV' in source


def test_env_example_documents_fail_closed_keys():
    example = (Path(settings.BASE_DIR) / '.env.example').read_text(encoding='utf-8')
    for key in ('DJANGO_ENV', 'SECRET_KEY', 'DEBUG', 'DATABASE_URL', 'PAYMENT_GATEWAY'):
        assert key in example


def test_mock_gateway_allowed_in_debug_or_pytest():
    assert mock_gateway_allowed(debug=True) is True
    assert mock_gateway_allowed(debug=False) is True  # pytest process


@override_settings(DEBUG=False, PAYMENT_GATEWAY='mock')
def test_get_gateway_still_serves_mock_inside_pytest():
    assert isinstance(get_gateway(), MockGateway)


@override_settings(DEBUG=False, PAYMENT_GATEWAY='mock')
def test_get_gateway_refuses_mock_when_not_a_test_process(monkeypatch):
    monkeypatch.setattr('config.security.running_under_pytest', lambda: False)
    with pytest.raises(ImproperlyConfigured, match='PAYMENT_GATEWAY=mock'):
        get_gateway()
