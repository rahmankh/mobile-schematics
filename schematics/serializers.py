from rest_framework import serializers
from .models import Brand, PhoneModel, SchematicCategory, Schematic, SchematicFile


class BrandSerializer(serializers.ModelSerializer):
    """
    Serializer for Brand listing with phone models count.
    """
    models_count = serializers.IntegerField(source='phone_models.count', read_only=True)

    class Meta:
        model = Brand
        fields = ['id', 'name', 'slug', 'logo', 'models_count']


class PhoneModelSerializer(serializers.ModelSerializer):
    """
    Serializer for PhoneModel with related brand info.
    """
    brand_name = serializers.CharField(source='brand.name', read_only=True)

    class Meta:
        model = PhoneModel
        fields = ['id', 'name', 'slug', 'technical_code', 'brand', 'brand_name']


class SchematicCategorySerializer(serializers.ModelSerializer):
    """
    Serializer for Schematic Categories.
    """
    class Meta:
        model = SchematicCategory
        fields = ['id', 'title', 'slug', 'description']


class SchematicFileListSerializer(serializers.ModelSerializer):
    """
    Serializer to expose file metadata without direct download link for unauthorized users.
    """
    class Meta:
        model = SchematicFile
        fields = ['id', 'file_title', 'file_size_bytes', 'created_at']


class SchematicListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for listing schematics on search/home pages.
    """
    brand_name = serializers.CharField(source='phone_model.brand.name', read_only=True)
    phone_model_name = serializers.CharField(source='phone_model.name', read_only=True)
    technical_code = serializers.CharField(source='phone_model.technical_code', read_only=True)
    category_title = serializers.CharField(source='category.title', read_only=True)
    files_count = serializers.IntegerField(source='files.count', read_only=True)

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
    """
    Detailed serializer including troubleshooting notes and attached file objects.
    """
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