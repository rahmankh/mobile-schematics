"""
REST serializers for the schematics catalog.

Public list/detail payloads never include a raw filesystem or MEDIA path.
File downloads are exposed only as a reverse() of `schematics:schematic-file-download`,
which is an authenticated, permission-checked streaming endpoint.
"""

from rest_framework import serializers

from .models import Brand, PhoneModel, Schematic, SchematicCategory, SchematicFile, SchematicPurchase


class BrandSerializer(serializers.ModelSerializer):
    """
    Brand row for the home catalog.

    `models_count` is injected by BrandListView via annotate(Count('phone_models')).
    It is NOT `phone_models.count` in Python — that would N+1 query per brand.
    """

    models_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Brand
        fields = ['id', 'name', 'slug', 'logo', 'models_count']


class PhoneModelSerializer(serializers.ModelSerializer):
    """Phone model with denormalized brand name for list cells that skip an extra join on the client."""

    brand_name = serializers.CharField(source='brand.name', read_only=True)

    class Meta:
        model = PhoneModel
        fields = ['id', 'name', 'slug', 'technical_code', 'brand', 'brand_name']


class SchematicCategorySerializer(serializers.ModelSerializer):
    """Category used both as a filter chip and as a nested object on schematic detail."""

    class Meta:
        model = SchematicCategory
        fields = ['id', 'title', 'slug', 'description']


class SchematicFileListSerializer(serializers.ModelSerializer):
    """
    Public file metadata for schematic detail.

    `download_url` MUST reverse `schematics:schematic-file-download` (the name
    declared in schematics/urls.py). A mismatched view_name raises NoReverseMatch
    and 500s the entire detail endpoint.
    """

    download_url = serializers.HyperlinkedIdentityField(
        view_name='schematics:schematic-file-download',
        lookup_field='pk',
    )

    class Meta:
        model = SchematicFile
        fields = ['id', 'file_title', 'file_size_bytes', 'download_url', 'created_at']
        # Intentionally omit `file` — FileField would call storage.url() or expose a MEDIA path.


class SchematicListSerializer(serializers.ModelSerializer):
    """
    Compact card payload for search / home lists.

    `files_count` is annotated in SchematicListView; default=0 keeps unit tests
    that instantiate the serializer without a queryset from crashing.
    """

    brand_name = serializers.CharField(source='phone_model.brand.name', read_only=True)
    phone_model_name = serializers.CharField(source='phone_model.name', read_only=True)
    technical_code = serializers.CharField(source='phone_model.technical_code', read_only=True)
    category_title = serializers.CharField(source='category.title', read_only=True)
    files_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Schematic
        fields = [
            'id',
            'title',
            'brand_name',
            'phone_model_name',
            'technical_code',
            'category_title',
            'is_free',
            'price',
            'requires_subscription',
            'files_count',
            'created_at',
        ]


class SchematicDetailSerializer(serializers.ModelSerializer):
    """Full schematic document including nested files with gated download URLs."""

    phone_model = PhoneModelSerializer(read_only=True)
    category = SchematicCategorySerializer(read_only=True)
    files = SchematicFileListSerializer(many=True, read_only=True)

    class Meta:
        model = Schematic
        fields = [
            'id',
            'title',
            'description',
            'phone_model',
            'category',
            'is_free',
            'price',
            'requires_subscription',
            'view_count',
            'files',
            'created_at',
            'updated_at',
        ]


class SchematicFileSerializer(serializers.ModelSerializer):
    """Write serializer for admin/API uploads. Not used for public download."""

    class Meta:
        model = SchematicFile
        fields = ['id', 'schematic', 'file', 'file_title', 'file_size_bytes', 'created_at']
        read_only_fields = ['id', 'file_size_bytes', 'created_at']


class SchematicPurchaseSerializer(serializers.ModelSerializer):
    """Read-only ledger payload for purchases the authenticated technician already owns."""

    schematic_title = serializers.CharField(source='schematic.title', read_only=True)

    class Meta:
        model = SchematicPurchase
        fields = ['id', 'schematic', 'schematic_title', 'price_paid', 'created_at']
        read_only_fields = fields


class SchematicPurchaseCheckoutSerializer(serializers.Serializer):
    """
    Input for starting a single-copy checkout.

    `schematic_id` is resolved to a Schematic instance; the view still must not
    insert SchematicPurchase until payment verify succeeds.
    """

    schematic_id = serializers.IntegerField()

    def validate_schematic_id(self, value: int) -> Schematic:
        try:
            return Schematic.objects.get(pk=value)
        except Schematic.DoesNotExist as exc:
            raise serializers.ValidationError('شماتیک مورد نظر یافت نشد.') from exc

