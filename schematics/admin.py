"""Single-page Django admin for publishing a schematic (model, file, price)."""

from __future__ import annotations

import os

from django import forms
from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .admin_widgets import ProtectedAdminFileWidget
from .models import Brand, PhoneModel, Schematic, SchematicCategory, SchematicFile, SchematicPurchase


class SchematicAdminForm(forms.ModelForm):
    """Compact create/edit form: model, title, price, and free/paid status."""

    class Meta:
        model = Schematic
        fields = ('phone_model', 'category', 'title', 'is_free', 'price', 'description')
        labels = {
            'phone_model': _('برند و مدل گوشی'),
            'category': _('دسته‌بندی'),
            'title': _('عنوان'),
            'is_free': _('رایگان'),
            'price': _('قیمت (تومان)'),
            'description': _('توضیحات'),
        }
        help_texts = {
            'phone_model': _('برند از روی مدل مشخص می‌شود. مدل را جستجو و انتخاب کنید.'),
            'is_free': _('اگر فعال باشد، کاربران واردشده بدون خرید نقشه را می‌بینند.'),
            'price': _('برای نقشه پولی عددی بزرگ‌تر از صفر وارد کنید. نقشه رایگان روی ۰ ذخیره می‌شود.'),
            'title': _('نام نمایشی در کاتالوگ و صفحه شماتیک.'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['description'].required = False
        self.fields['price'].widget.attrs.setdefault('min', '0')
        self.fields['price'].widget.attrs.setdefault('inputmode', 'numeric')

    def clean(self):
        cleaned = super().clean()
        is_free = cleaned.get('is_free')
        price = cleaned.get('price')
        if is_free:
            cleaned['price'] = 0
        elif price is not None and price <= 0:
            self.add_error(
                'price',
                _('برای نقشه پولی، قیمت باید بزرگ‌تر از صفر باشد.'),
            )
        return cleaned


class SchematicFileInlineForm(forms.ModelForm):
    """File row on the schematic form. Title is optional and follows the filename."""

    class Meta:
        model = SchematicFile
        fields = ('file', 'file_title')
        widgets = {
            'file': ProtectedAdminFileWidget,
        }
        labels = {
            'file': _('فایل نقشه / بردویو'),
            'file_title': _('عنوان فایل'),
        }
        help_texts = {
            'file': _('PDF، تصویر بردویو، یا ZIP. حداکثر یک فایل برای انتشار کافی است.'),
            'file_title': _('اگر خالی بماند از نام فایل استفاده می‌شود.'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['file_title'].required = False

    def clean(self):
        cleaned = super().clean()
        uploaded = cleaned.get('file')
        title = (cleaned.get('file_title') or '').strip()
        if uploaded and not title:
            cleaned['file_title'] = os.path.basename(getattr(uploaded, 'name', '') or 'file')[:150]
        return cleaned


class SchematicFileInline(admin.StackedInline):
    """Upload the schematic binary on the same page as price and model."""

    model = SchematicFile
    form = SchematicFileInlineForm
    extra = 1
    min_num = 1
    validate_min = True
    max_num = 5
    fields = ('file', 'file_title')
    verbose_name = _('فایل نقشه')
    verbose_name_plural = _('آپلود فایل')


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'created_at')
    search_fields = ('name',)
    prepopulated_fields = {'slug': ('name',)}


@admin.register(PhoneModel)
class PhoneModelAdmin(admin.ModelAdmin):
    list_display = ('name', 'brand', 'technical_code', 'created_at')
    list_filter = ('brand',)
    search_fields = ('name', 'technical_code', 'brand__name')
    prepopulated_fields = {'slug': ('name',)}
    autocomplete_fields = ('brand',)


@admin.register(SchematicCategory)
class SchematicCategoryAdmin(admin.ModelAdmin):
    list_display = ('title', 'slug')
    search_fields = ('title', 'slug')
    prepopulated_fields = {'slug': ('title',)}


@admin.register(Schematic)
class SchematicAdmin(admin.ModelAdmin):
    """
    One admin screen to publish a schematic: pick the phone model, set price
    or free status, and upload the file. Subscription flags, view counters,
    and timestamps stay off the form.
    """

    form = SchematicAdminForm
    inlines = [SchematicFileInline]
    save_on_top = True
    list_select_related = ('phone_model__brand', 'category')
    autocomplete_fields = ('phone_model', 'category')
    list_display = (
        'title',
        'phone_model',
        'category',
        'is_free',
        'price',
        'created_at',
    )
    list_filter = ('is_free', 'category', 'phone_model__brand')
    search_fields = (
        'title',
        'phone_model__name',
        'phone_model__brand__name',
        'phone_model__technical_code',
    )
    fieldsets = (
        (
            _('مدل گوشی'),
            {
                'classes': ('wide',),
                'fields': ('phone_model', 'category', 'title'),
                'description': _('برند و مدل را از فهرست مدل‌ها انتخاب کنید؛ نیازی به صفحه جداگانه نیست.'),
            },
        ),
        (
            _('قیمت و وضعیت'),
            {
                'classes': ('wide',),
                'fields': ('is_free', 'price'),
            },
        ),
        (
            _('توضیحات (اختیاری)'),
            {
                'classes': ('collapse',),
                'fields': ('description',),
            },
        ),
    )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'phone_model':
            kwargs['queryset'] = PhoneModel.objects.select_related('brand').order_by(
                'brand__name',
                'name',
            )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(SchematicPurchase)
class SchematicPurchaseAdmin(admin.ModelAdmin):
    """
    Read-mostly ledger of single-copy purchases.

    Unique (user, schematic) is enforced at the database. Prefer letting the
    payment verify() path create rows; manual admin adds are for support only.
    """

    list_display = ('user', 'schematic', 'price_paid', 'created_at')
    list_filter = ('created_at', 'schematic__phone_model__brand', 'schematic__category')
    search_fields = (
        'user__phone_number',
        'user__first_name',
        'user__last_name',
        'schematic__title',
        'schematic__phone_model__name',
    )
    date_hierarchy = 'created_at'
    raw_id_fields = ('user', 'schematic')
    readonly_fields = ('created_at',)
