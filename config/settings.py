"""
Django settings for the mobile-schematics API.

All secrets and environment-specific values are loaded via django-environ.
Never commit a real SECRET_KEY. Copy `.env.example` to `.env` for local work.
"""

from __future__ import annotations

from pathlib import Path

import environ
from django.utils.translation import gettext_lazy as _

BASE_DIR = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
# Defaults are safe for tests/CI (DEBUG off, SQLite, no SSL redirect).
# Production MUST set SECRET_KEY, DEBUG=False, ALLOWED_HOSTS, and DATABASE_URL.
env = environ.Env(
    DEBUG=(bool, False),
    SECRET_KEY=(str, 'django-insecure-dev-only-change-me'),
    ALLOWED_HOSTS=(list, ['localhost', '127.0.0.1', 'testserver']),
    CSRF_TRUSTED_ORIGINS=(list, []),
    CORS_ALLOWED_ORIGINS=(list, [
        'http://localhost:3000',
        'http://127.0.0.1:3000',
        'http://localhost:5173',
        'http://127.0.0.1:5173',
    ]),
    CORS_ALLOW_CREDENTIALS=(bool, True),
    SERVE_MEDIA=(bool, False),
    SECURE_SSL_REDIRECT=(bool, False),
    SESSION_COOKIE_SECURE=(bool, False),
    CSRF_COOKIE_SECURE=(bool, False),
    SECURE_HSTS_SECONDS=(int, 0),
)

_env_file = BASE_DIR / '.env'
if _env_file.exists():
    # overwrite=False: real OS env vars (CI, Docker, systemd) win over .env.
    environ.Env.read_env(_env_file, overwrite=False)

SECRET_KEY = env('SECRET_KEY')
DEBUG = env.bool('DEBUG')
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS')

# ---------------------------------------------------------------------------
# Application definition
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Third-party
    'corsheaders',
    'rest_framework',
    'rest_framework_simplejwt',
    'drf_spectacular',
    # Local
    'accounts',
    'schematics',
    'subscriptions',
    'payments',
    'web',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    # CorsMiddleware must sit above CommonMiddleware so preflight OPTIONS are answered.
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# ---------------------------------------------------------------------------
# Database — SQLite by default, PostgreSQL (or any engine) via DATABASE_URL
# Examples:
#   sqlite:     sqlite:///BASE_DIR/db.sqlite3   (built below)
#   postgres:   postgres://USER:PASSWORD@HOST:5432/DBNAME
# ---------------------------------------------------------------------------
_default_sqlite = 'sqlite:///' + (BASE_DIR / 'db.sqlite3').as_posix()
DATABASES = {
    'default': env.db('DATABASE_URL', default=_default_sqlite),
}
# Persistent connections help Postgres in production; 0 is correct for SQLite + tests.
DATABASES['default']['CONN_MAX_AGE'] = env.int('CONN_MAX_AGE', default=0)

# Rate-limit counters. LocMem is process-local (fine for tests/dev); use Redis in prod.
CACHES = {
    'default': env.cache('CACHE_URL', default='locmemcache://'),
}

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
AUTH_USER_MODEL = 'accounts.CustomUser'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ---------------------------------------------------------------------------
# I18N
# ---------------------------------------------------------------------------
LANGUAGE_CODE = 'fa-ir'
TIME_ZONE = env('TIME_ZONE', default='UTC')
USE_I18N = True
USE_TZ = True

LANGUAGES = [
    ('fa', _('فارسی')),
    ('en', 'English'),
]

LOCALE_PATHS = [BASE_DIR / 'locale']

# ---------------------------------------------------------------------------
# Static & media
# ---------------------------------------------------------------------------
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Public uploads only (brand logos). Served via serve_public_media when DEBUG/SERVE_MEDIA.
MEDIA_URL = '/media/'
MEDIA_ROOT = env.path('MEDIA_ROOT', default=BASE_DIR / 'media')

# Paid schematic binaries — NEVER served via MEDIA_URL. See schematics.storage.
PROTECTED_MEDIA_ROOT = env.path('PROTECTED_MEDIA_ROOT', default=BASE_DIR / 'protected_media')

# When True, Django will serve public MEDIA_ROOT files (still denying protected_schematics/).
# Production should keep this False and let nginx serve MEDIA_ROOT with a location deny.
SERVE_MEDIA = env.bool('SERVE_MEDIA', default=DEBUG)

# ---------------------------------------------------------------------------
# Email — Django 6.1 uses MAILERS (EMAIL_BACKEND is deprecated).
# ---------------------------------------------------------------------------
MAILERS = {
    'default': {
        'BACKEND': env(
            'EMAIL_BACKEND',
            default='django.core.mail.backends.console.EmailBackend',
        ),
    },
}

# ---------------------------------------------------------------------------
# DRF / JWT
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticatedOrReadOnly',
    ),
    'DEFAULT_FILTER_BACKENDS': (
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ),
    'DEFAULT_PAGINATION_CLASS': 'config.pagination.StandardResultsSetPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_THROTTLE_RATES': {
        # login covers register + token refresh as well (same IP budget).
        'login': '10/minute',
        # Reserved for SMS OTP views; stricter because each send is billable.
        'otp': '5/minute',
        'downloads': '30/minute',
        'guest_checkout': '20/minute',
    },
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

# OpenAPI 3 schema + Swagger UI at /api/docs/ (schema JSON/YAML at /api/schema/).
SPECTACULAR_SETTINGS = {
    'TITLE': 'Mobile Schematics API',
    'DESCRIPTION': (
        'REST API for the technician schematic catalog: JWT auth, catalog browse, '
        'gated file downloads, subscriptions, and payment checkout.'
    ),
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'SCHEMA_PATH_PREFIX': r'/api/v1',
    'COMPONENT_SPLIT_REQUEST': True,
    'TAGS': [
        {'name': 'accounts', 'description': 'Registration, JWT login, and technician profile.'},
        {'name': 'schematics', 'description': 'Catalog browse, single-copy checkout, and gated downloads.'},
        {'name': 'subscriptions', 'description': 'Plans and the caller\'s current entitlement.'},
        {'name': 'payments', 'description': 'Gateway request/verify. Content unlocks only after verify.'},
    ],
}

# ---------------------------------------------------------------------------
# CSRF / proxy / HTTPS hardening (opt-in via env so tests stay on HTTP)
# ---------------------------------------------------------------------------
# Browser / Expo-web clients. Native mobile apps do not use CORS; keep this list tight.
CORS_ALLOWED_ORIGINS = env.list('CORS_ALLOWED_ORIGINS')
CORS_ALLOW_CREDENTIALS = env.bool('CORS_ALLOW_CREDENTIALS')
CORS_ALLOWED_ORIGIN_REGEXES = env.list('CORS_ALLOWED_ORIGIN_REGEXES', default=[])
CORS_ALLOW_HEADERS = list(
    {
        'accept',
        'authorization',
        'content-type',
        'origin',
        'user-agent',
        'x-csrftoken',
        'x-requested-with',
    }
)

CSRF_TRUSTED_ORIGINS = env.list(
    'CSRF_TRUSTED_ORIGINS',
    default=[
        'https://*.app.github.dev',
        'https://*.githubpreview.dev',
    ],
)

SECURE_SSL_REDIRECT = env.bool('SECURE_SSL_REDIRECT')
SESSION_COOKIE_SECURE = env.bool('SESSION_COOKIE_SECURE')
CSRF_COOKIE_SECURE = env.bool('CSRF_COOKIE_SECURE')
SECURE_HSTS_SECONDS = env.int('SECURE_HSTS_SECONDS')
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool('SECURE_HSTS_INCLUDE_SUBDOMAINS', default=False)
SECURE_HSTS_PRELOAD = env.bool('SECURE_HSTS_PRELOAD', default=False)
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# HTML catalog (web app) uses Django sessions. The mobile API still uses JWT.
LOGIN_URL = 'web:login'
LOGIN_REDIRECT_URL = 'web:home'
LOGOUT_REDIRECT_URL = 'web:home'

# Payment adapters. Keep PAYMENT_GATEWAY=mock until Zarinpal/IDPay keys exist.
PAYMENT_GATEWAY = env('PAYMENT_GATEWAY', default='mock')
PAYMENT_CALLBACK_URL = env('PAYMENT_CALLBACK_URL', default='')
PAYMENT_START_URL_TEMPLATE = env(
    'PAYMENT_START_URL_TEMPLATE',
    default='https://sandbox.zarinpal.com/pg/StartPay/{authority}',
)
PAYMENT_MOCK_SUCCESS = env.bool('PAYMENT_MOCK_SUCCESS', default=True)
PAYMENT_ZARINPAL_MERCHANT_ID = env('PAYMENT_ZARINPAL_MERCHANT_ID', default='')
PAYMENT_IDPAY_API_KEY = env('PAYMENT_IDPAY_API_KEY', default='')
