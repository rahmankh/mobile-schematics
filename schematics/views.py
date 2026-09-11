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
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema, extend_schema_view

from config.throttling import DownloadRateThrottle
from .access import denied_download_payload

from .models import Brand, PhoneModel, Schematic, SchematicCategory, SchematicFile, SchematicPurchase
from .serializers import (
    BrandSerializer,
    PhoneModelSerializer,
    SchematicCategorySerializer,
    SchematicDetailSerializer,
    SchematicListSerializer,
    SchematicPurchaseCheckoutSerializer,
    SchematicPurchaseSerializer,
)
from .services import AlreadyPurchased, SchematicNotPurchasable, assert_schematic_purchasable


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

    @extend_schema(
        parameters=[
            OpenApiParameter(
                'brand',
                OpenApiTypes.STR,
                OpenApiParameter.QUERY,
                description='Filter by Brand.slug (e.g. samsung).',
            ),
        ],
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        queryset = PhoneModel.objects.select_related('brand').all()
        brand_slug = self.request.query_params.get('brand')
        if brand_slug:
            queryset = queryset.filter(brand__slug=brand_slug)
        # Explicit order: annotate/filter can drop Meta.ordering and break pages.
        return queryset.order_by('brand__name', 'name', 'pk')


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

    @extend_schema(
        parameters=[
            OpenApiParameter(
                'category',
                OpenApiTypes.STR,
                OpenApiParameter.QUERY,
                description='Filter by SchematicCategory.slug.',
            ),
            OpenApiParameter(
                'model_id',
                OpenApiTypes.INT,
                OpenApiParameter.QUERY,
                description='Filter by PhoneModel primary key.',
            ),
        ],
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

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

        # Count() annotations drop Meta.ordering; pin a stable page order.
        return queryset.order_by('-created_at', 'pk')


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


@extend_schema(
    tags=['schematics'],
    responses={
        200: OpenApiResponse(description='Binary file (Content-Disposition: attachment).'),
        403: OpenApiResponse(description='Caller is not entitled to this schematic.'),
        404: OpenApiResponse(description='File row or bytes are missing.'),
    },
)
class SchematicFileDownloadView(APIView):
    """
    GET /api/v1/schematics/files/<id>/download/

    Streams the binary from ProtectedSchematicStorage after Schematic.user_can_download
    succeeds. Anonymous callers get 401 with `code=login_required` (Persian copy +
    guest-checkout hint) instead of DRF's default English 403/401.
    """

    permission_classes = [AllowAny]
    throttle_classes = [DownloadRateThrottle]

    def get(self, request, pk, *args, **kwargs):
        try:
            schematic_file = SchematicFile.objects.select_related(
                'schematic',
                'schematic__phone_model__brand',
            ).get(pk=pk)
        except SchematicFile.DoesNotExist as exc:
            raise Http404(_('فایل مورد نظر یافت نشد.')) from exc

        if not schematic_file.schematic.user_can_download(request.user):
            payload, http_status = denied_download_payload(
                request.user,
                schematic_file.schematic,
            )
            return Response(payload, status=http_status)

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


@extend_schema_view(
    get=extend_schema(tags=['schematics'], responses=SchematicPurchaseSerializer(many=True)),
    post=extend_schema(
        tags=['schematics'],
        request=SchematicPurchaseCheckoutSerializer,
        responses={
            402: OpenApiResponse(description='Payment required; client must POST /api/v1/payments/request/.'),
            400: OpenApiResponse(description='Schematic is not purchasable.'),
            409: OpenApiResponse(description='Already owned.'),
        },
    ),
)
class SchematicPurchaseListCreateView(APIView):
    """
    GET  /api/v1/schematics/purchases/  — ledger of schematics this user already owns.
    POST /api/v1/schematics/purchases/  — start checkout (does NOT insert a purchase).

    POST returns 402 Payment Required with amount + schematic_id. The client must
    call POST /api/v1/payments/request/ and only after verify() will
    fulfill_schematic_purchase run.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset = (
            SchematicPurchase.objects.filter(user=request.user)
            .select_related('schematic', 'schematic__phone_model__brand')
            .order_by('-created_at')
        )
        return Response(SchematicPurchaseSerializer(queryset, many=True).data)

    def post(self, request):
        serializer = SchematicPurchaseCheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        schematic = serializer.validated_data['schematic_id']

        try:
            assert_schematic_purchasable(request.user, schematic)
        except AlreadyPurchased as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_409_CONFLICT)
        except SchematicNotPurchasable as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                'detail': _('پرداخت قبل از فعال‌سازی خرید تکی الزامی است.'),
                'purpose': 'schematic',
                'schematic_id': schematic.pk,
                'amount': schematic.price,
            },
            status=status.HTTP_402_PAYMENT_REQUIRED,
        )

