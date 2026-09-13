# schematics/urls.py

from django.urls import path
from .views import (
    BrandListView,
    PhoneModelListView,
    SchematicCategoryListView,
    SchematicDetailView,
    SchematicFileDownloadView,
    SchematicFileViewStreamView,
    SchematicListView,
    SchematicPurchaseListCreateView,
)

app_name = 'schematics'

urlpatterns = [
    path('brands/', BrandListView.as_view(), name='brand-list'),
    path('models/', PhoneModelListView.as_view(), name='phone-model-list'),
    path('categories/', SchematicCategoryListView.as_view(), name='category-list'),
    path('purchases/', SchematicPurchaseListCreateView.as_view(), name='purchase-list'),
    path('', SchematicListView.as_view(), name='schematic-list'),
    path('<int:pk>/', SchematicDetailView.as_view(), name='schematic-detail'),
    path('files/<int:pk>/view/', SchematicFileViewStreamView.as_view(), name='schematic-file-view'),
    path('files/<int:pk>/download/', SchematicFileDownloadView.as_view(), name='schematic-file-download'),
]