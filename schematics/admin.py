"""Django admin for the schematic catalog and purchase ledger."""

from django.contrib import admin

from .models import Brand, PhoneModel, Schematic, SchematicCategory, SchematicFile, SchematicPurchase


class SchematicFileInline(admin.TabularInline):
    """Edit attached binaries on the schematic change page. Size is computed on save."""

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
    list_display = (
        'title',
        'phone_model',
        'category',
        'is_free',
        'price',
        'requires_subscription',
        'view_count',
        'created_at',
    )
    list_filter = ('category', 'is_free', 'requires_subscription', 'phone_model__brand')
    search_fields = ('title', 'description', 'phone_model__name', 'phone_model__technical_code')
    inlines = [SchematicFileInline]


@admin.register(SchematicPurchase)
class SchematicPurchaseAdmin(admin.ModelAdmin):
    """
    Read-mostly ledger of single-copy purchases.

    Unique (user, schematic) is enforced at the database; the admin should not
    be used to create duplicates.
    """

    list_display = ('user', 'schematic', 'price_paid', 'created_at')
    list_filter = ('created_at',)
    search_fields = (
        'user__phone_number',
        'user__first_name',
        'user__last_name',
        'schematic__title',
    )
    raw_id_fields = ('user', 'schematic')
    readonly_fields = ('created_at',)
