from django.urls import path
from .views import (
    BrandListView,
    PhoneModelListView,
    SchematicCategoryListView,
    SchematicListView,
    SchematicDetailView,
)

app_name = 'schematics'

urlpatterns = [
    path('brands/', BrandListView.as_view(), name='brand-list'),
    path('models/', PhoneModelListView.as_view(), name='model-list'),
    path('categories/', SchematicCategoryListView.as_view(), name='category-list'),
    path('list/', SchematicListView.as_view(), name='schematic-list'),
    path('detail/<int:pk>/', SchematicDetailView.as_view(), name='schematic-detail'),
]