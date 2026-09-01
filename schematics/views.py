from django.db.models import F
from django.utils.translation import gettext_lazy as _
from rest_framework import generics, filters
from rest_framework.permissions import AllowAny, IsAuthenticated

# ایمپورت پرمیشن اختصاصی اشتراک
from subscriptions.permissions import HasActiveSubscription

# اضافه شدن SchematicFile به ایمپورت مدل‌ها
from .models import Brand, PhoneModel, SchematicCategory, Schematic, SchematicFile
from .serializers import (
    BrandSerializer,
    PhoneModelSerializer,
    SchematicCategorySerializer,
    SchematicListSerializer,
    SchematicDetailSerializer,
    SchematicFileSerializer,  # مطمئن شوید این سریالایزر در serializers.py تعریف شده باشد
)


class BrandListView(generics.ListAPIView):
    """
    لیست تمامی برندهای موبایل همراه با تعداد مدل‌های ثبت‌شده.
    List all mobile brands with model counts.
    """
    queryset = Brand.objects.all().prefetch_related('phone_models')
    serializer_class = BrandSerializer
    permission_classes = [AllowAny]
    filter_backends = [filters.SearchFilter]
    search_fields = ['name']


class PhoneModelListView(generics.ListAPIView):
    """
    لیست مدل‌های گوشی با قابلیت فیلتر بر اساس برند.
    List phone models filterable by brand.
    """
    serializer_class = PhoneModelSerializer
    permission_classes = [AllowAny]
    filter_backends = [filters.SearchFilter]
    search_fields = ['name', 'technical_code']

    def get_queryset(self):
        queryset = PhoneModel.objects.select_related('brand').all()
        brand_slug = self.request.query_params.get('brand')
        if brand_slug:
            queryset = queryset.filter(brand__slug=brand_slug)
        return queryset


class SchematicCategoryListView(generics.ListAPIView):
    """
    لیست دسته‌بندی‌های شماتیک (نقشه کامل، سلوشن، تست‌پوینت).
    List schematic categories.
    """
    queryset = SchematicCategory.objects.all()
    serializer_class = SchematicCategorySerializer
    permission_classes = [AllowAny]


class SchematicListView(generics.ListAPIView):
    """
    جستجو و مشاهده لیست شماتیک‌ها با کوئری‌های بهینه.
    List and search schematics with high performance database joins.
    """
    serializer_class = SchematicListSerializer
    permission_classes = [AllowAny]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = [
        'title',
        'phone_model__name',
        'phone_model__technical_code',
        'phone_model__brand__name'
    ]
    ordering_fields = ['created_at', 'price', 'view_count']

    def get_queryset(self):
        queryset = Schematic.objects.select_related(
            'phone_model__brand',
            'category'
        ).prefetch_related('files').all()

        category_slug = self.request.query_params.get('category')
        phone_model_id = self.request.query_params.get('model_id')

        if category_slug:
            queryset = queryset.filter(category__slug=category_slug)
        if phone_model_id:
            queryset = queryset.filter(phone_model_id=phone_model_id)

        return queryset


class SchematicDetailView(generics.RetrieveAPIView):
    """
    مشاهده جزئیات کامل شماتیک و افزایش شمارنده بازدید.
    Retrieve single schematic details and increment view count.
    """
    serializer_class = SchematicDetailSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return Schematic.objects.select_related(
            'phone_model__brand',
            'category'
        ).prefetch_related('files').all()

    def get_object(self):
        obj = super().get_object()
        Schematic.objects.filter(pk=obj.pk).update(view_count=F('view_count') + 1)
        obj.refresh_from_db()
        return obj


# =========================================================================
# بخش جدید: کنترل دسترسی دانلود فایل‌های شماتیک بر اساس اشتراک فعال
# =========================================================================
class SchematicFileDownloadView(generics.RetrieveAPIView):
    """
    مشاهده و دانلود فایل شماتیک.
    فقط کاربران دارای اشتراک فعال (یا ادمین‌ها) مجاز به دریافت فایل هستند.
    """
    queryset = SchematicFile.objects.select_related('schematic').all()
    serializer_class = SchematicFileSerializer
    permission_classes = [IsAuthenticated, HasActiveSubscription]