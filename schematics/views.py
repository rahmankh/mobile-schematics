"""
Catalog and gated-download HTTP endpoints for schematics.

Download is the only path that streams bytes. List/detail are public reads;
entitlement is enforced when the client hits SchematicFileDownloadView.
"""

from __future__ import annotations

import os

from django.db.models import Count, F
from django.http import FileResponse, Http404
from django.utils.translation import gettext_lazy as _
from rest_framework import filters, generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Brand, PhoneModel, Schematic, SchematicCategory, SchematicFile
from .serializers import (
    BrandSerializer,
    PhoneModelSerializer,
    SchematicCategorySerializer,
    SchematicDetailSerializer,
    SchematicListSerializer,
)


class BrandListView(generics.ListAPIView):
    """
    GET /api/v1/schematics/brands/

    Returns every brand with `models_count` computed in SQL (no N+1).
    Public: technicians browse the catalog before signing in.
    """

    serializer_class = BrandSerializer
    permission_classes = [AllowAny]
    filter_backends = [filters.SearchFilter]
    search_fields = ['name']

    def get_queryset(self):
        return Brand.objects.annotate(models_count=Count('phone_models')).order_by('name')


class PhoneModelListView(generics.ListAPIView):
    """
    GET /api/v1/schematics/models/?brand=<slug>&search=

    Optional `brand` query param filters by Brand.slug.
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
    """GET /api/v1/schematics/categories/ — public filter chips."""

    queryset = SchematicCategory.objects.all()
    serializer_class = SchematicCategorySerializer
    permission_classes = [AllowAny]


class SchematicListView(generics.ListAPIView):
    """
    GET /api/v1/schematics/?category=<slug>&model_id=<id>&search=&ordering=

    Joins brand/model/category in one query and annotates files_count.
    """

    serializer_class = SchematicListSerializer
    permission_classes = [AllowAny]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = [
        'title',
        'phone_model__name',
        'phone_model__technical_code',
        'phone_model__brand__name',
    ]
    ordering_fields = ['created_at', 'price', 'view_count']

    def get_queryset(self):
        queryset = Schematic.objects.select_related(
            'phone_model__brand',
            'category',
        ).annotate(
            files_count=Count('files'),
        )

        category_slug = self.request.query_params.get('category')
        phone_model_id = self.request.query_params.get('model_id')

        if category_slug:
            queryset = queryset.filter(category__slug=category_slug)
        if phone_model_id:
            queryset = queryset.filter(phone_model_id=phone_model_id)

        return queryset


class SchematicDetailView(generics.RetrieveAPIView):
    """
    GET /api/v1/schematics/<id>/

    Increments view_count atomically with F() so concurrent reads cannot clobber
    each other. Nested files include a reverse() download URL, not a MEDIA path.
    """

    serializer_class = SchematicDetailSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return Schematic.objects.select_related(
            'phone_model__brand',
            'category',
        ).prefetch_related('files')

    def get_object(self):
        obj = super().get_object()
        Schematic.objects.filter(pk=obj.pk).update(view_count=F('view_count') + 1)
        obj.refresh_from_db(fields=['view_count'])
        return obj


class SchematicFileDownloadView(APIView):
    """
    GET /api/v1/schematics/files/<id>/download/

    Streams the binary from ProtectedSchematicStorage after Schematic.user_can_download
    succeeds. Never redirects to /media/; the file handle comes from storage.open().
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, pk, *args, **kwargs):
        try:
            schematic_file = SchematicFile.objects.select_related(
                'schematic',
                'schematic__phone_model__brand',
            ).get(pk=pk)
        except SchematicFile.DoesNotExist as exc:
            raise Http404(_('فایل مورد نظر یافت نشد.')) from exc

        if not schematic_file.schematic.user_can_download(request.user):
            return Response(
                {
                    'detail': _(
                        'برای دانلود این فایل باید اشتراک فعال تهیه کنید '
                        'یا نقشه را به صورت تکی خریداری نمایید.'
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        if not schematic_file.file:
            return Response(
                {'detail': _('فایل فیزیکی روی سرور موجود نیست.')},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            # Storage-agnostic open: works for ProtectedSchematicStorage and test tmp dirs.
            file_handle = schematic_file.file.open('rb')
        except (FileNotFoundError, OSError, ValueError):
            return Response(
                {'detail': _('فایل فیزیکی روی سرور موجود نیست.')},
                status=status.HTTP_404_NOT_FOUND,
            )

        filename = os.path.basename(schematic_file.file.name)
        return FileResponse(
            file_handle,
            as_attachment=True,
            filename=filename,
        )
