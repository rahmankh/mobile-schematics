"""Root URL configuration for the mobile-schematics API."""

from django.contrib import admin
from django.urls import include, path

from config.media_views import serve_public_media

urlpatterns = [
    path('admin/', admin.site.urls),
    # Required by templates/admin/base_site.html language switcher.
    path('i18n/', include('django.conf.urls.i18n')),
    path('', include('web.urls')),
    path('api/v1/accounts/', include('accounts.urls')),
    path('api/v1/schematics/', include('schematics.urls')),
    path('api/v1/subscriptions/', include('subscriptions.urls')),
    path('api/v1/payments/', include('payments.urls')),
    # Public uploads (logos). The view refuses protected_schematics/ and honours SERVE_MEDIA.
    path('media/<path:path>', serve_public_media, name='public-media'),
]
