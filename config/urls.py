# config/urls.py

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import TemplateView

urlpatterns = [
    path('admin/', admin.site.urls),

    # صفحه اول بصورت رابط گرافیکی وب
    path('', TemplateView.as_view(template_name='home.html'), name='home'),

    # مسیرهای API
    path('api/v1/accounts/', include('accounts.urls')),
    path('api/v1/schematics/', include('schematics.urls')),
    path('api/v1/subscriptions/', include('subscriptions.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)