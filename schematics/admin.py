

from django.contrib import admin
from .models import Brand, PhoneModel, SchematicCategory, Schematic, SchematicFile


class SchematicFileInline(admin.TabularInline):
    model = SchematicFile
    extra = 1
    readonly_fields = ('file_size_bytes', 'created_at')


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'created_at')
    search_fields = ('name',)
    prepopulated_fields = {'slug': ('name',)}


@admin.register(PhoneModel)
class PhoneModelAdmin(admin.ModelAdmin):
    list_display = ('name', 'brand', 'technical_code', 'created_at')
    list_filter = ('brand',)
    search_fields = ('name', 'technical_code')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(SchematicCategory)
class SchematicCategoryAdmin(admin.ModelAdmin):
    list_display = ('title', 'slug')
    prepopulated_fields = {'slug': ('title',)}


@admin.register(Schematic)
class SchematicAdmin(admin.ModelAdmin):
    list_display = ('title', 'phone_model', 'category', 'is_free', 'price', 'requires_subscription', 'view_count', 'created_at')
    list_filter = ('category', 'is_free', 'requires_subscription', 'phone_model__brand')
    search_fields = ('title', 'description', 'phone_model__name', 'phone_model__technical_code')
    inlines = [SchematicFileInline]