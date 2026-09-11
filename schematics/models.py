"""
Catalog domain for mobile repair schematics.

Relationship overview
---------------------
Brand 1──* PhoneModel 1──* Schematic *──1 SchematicCategory
                              │
                              ├──* SchematicFile   (binaries live in PROTECTED_MEDIA_ROOT)
                              └──* SchematicPurchase (per-user single-copy entitlement)

Indexes and constraints are designed around the hot API paths:
list-by-brand, list-by-category, permission checks, and unique purchases.
"""

from __future__ import annotations

from django.conf import settings
from django.core.validators import FileExtensionValidator, MinValueValidator
from django.db import models
from django.utils.text import get_valid_filename, slugify
from django.utils.translation import gettext_lazy as _

from schematics.storage import protected_storage


def schematic_file_upload_path(instance, filename: str) -> str:
    """
    Build a namespaced relative path under PROTECTED_MEDIA_ROOT.

    Layout: protected_schematics/<brand-slug>/<model-slug>/<safe-filename>
    The `protected_schematics/` prefix is a second line of defence: even if a
    file were accidentally placed in MEDIA_ROOT, the public media view refuses
    that prefix.
    """
    brand_slug = instance.schematic.phone_model.brand.slug
    model_slug = instance.schematic.phone_model.slug
    safe_name = get_valid_filename(filename)
    return f"protected_schematics/{brand_slug}/{model_slug}/{safe_name}"


class Brand(models.Model):
    """
    Handset manufacturer shown on the home / catalog screen (Samsung, Xiaomi, ...).

    `name` and `slug` are both unique so API lookups by slug and admin data
    entry by name cannot diverge into duplicates.
    """

    name = models.CharField(_('نام برند'), max_length=100, unique=True)
    slug = models.SlugField(_('اسلاگ'), max_length=120, unique=True, allow_unicode=True)
    logo = models.ImageField(_('لوگو'), upload_to='brands/', blank=True, null=True)
    created_at = models.DateTimeField(_('تاریخ ایجاد'), auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name = _('برند')
        verbose_name_plural = _('برندها')

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        # Auto-slug only when empty so editors can keep a stable URL after a rename.
        if not self.slug:
            self.slug = slugify(self.name, allow_unicode=True)
        super().save(*args, **kwargs)


class PhoneModel(models.Model):
    """
    A specific device under a brand (e.g. Galaxy S24 Ultra / SM-S928B).

    Uniqueness is enforced on (brand, slug) for URLs and (brand, name) so the
    catalog cannot contain two "S24 Ultra" rows for Samsung with different slugs.
    """

    brand = models.ForeignKey(
        Brand,
        on_delete=models.CASCADE,
        related_name='phone_models',
        verbose_name=_('برند'),
    )
    name = models.CharField(_('نام مدل'), max_length=150)
    slug = models.SlugField(_('اسلاگ'), max_length=170, allow_unicode=True)
    technical_code = models.CharField(
        _('کد فنی / شناسه برد'),
        max_length=100,
        blank=True,
        db_index=True,
        help_text=_('مانند SM-S918B, A2638'),
    )
    created_at = models.DateTimeField(_('تاریخ ایجاد'), auto_now_add=True)

    class Meta:
        ordering = ['brand', 'name']
        verbose_name = _('مدل گوشی')
        verbose_name_plural = _('مدل‌های گوشی')
        constraints = [
            models.UniqueConstraint(
                fields=['brand', 'slug'],
                name='uniq_phonemodel_brand_slug',
            ),
            models.UniqueConstraint(
                fields=['brand', 'name'],
                name='uniq_phonemodel_brand_name',
            ),
        ]
        # (brand, name) and (brand, slug) uniqueness already create composite indexes.
        # technical_code keeps a standalone db_index for board-code search.

    def __str__(self) -> str:
        return f'{self.brand.name} - {self.name}'

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name, allow_unicode=True)
        super().save(*args, **kwargs)


class SchematicCategory(models.Model):
    """
    Catalog grouping for schematics (boardview, voltage rails, service manual, ...).

    Categories are shared across brands; they are not brand-specific.
    """

    title = models.CharField(_('عنوان دسته‌بندی'), max_length=100, unique=True)
    slug = models.SlugField(_('اسلاگ'), max_length=120, unique=True, allow_unicode=True)
    description = models.TextField(_('توضیحات'), blank=True)

    class Meta:
        ordering = ['title']
        verbose_name = _('دسته‌بندی نقشه')
        verbose_name_plural = _('دسته‌بندی‌های نقشه')

    def __str__(self) -> str:
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title, allow_unicode=True)
        super().save(*args, **kwargs)


class Schematic(models.Model):
    """
    A sellable / subscription-gated repair document for one phone model.

    Access matrix (see `user_can_download`):
    - `is_free=True`              → any authenticated user
    - staff / superuser           → always
    - matching SchematicPurchase  → single-copy buyer
    - `requires_subscription=True` + active UserSubscription → subscriber
    """

    phone_model = models.ForeignKey(
        PhoneModel,
        on_delete=models.CASCADE,
        related_name='schematics',
        verbose_name=_('مدل گوشی'),
    )
    category = models.ForeignKey(
        SchematicCategory,
        on_delete=models.PROTECT,
        related_name='schematics',
        verbose_name=_('دسته‌بندی'),
        # PROTECT: deleting a category that still has schematics would orphan catalog rows.
    )
    title = models.CharField(_('عنوان شماتیک'), max_length=255)
    description = models.TextField(
        _('نکات فنی و راه‌حل‌ها'),
        blank=True,
        help_text=_('توضیحات تخصصی عیب‌یابی و مسیرهای ولتاژ'),
    )
    is_free = models.BooleanField(
        _('رایگان'),
        default=False,
        db_index=True,
        help_text=_('در صورت فعال بودن، برای تمام کاربران احراز هویت‌شده بدون اشتراک قابل دانلود است.'),
    )
    price = models.DecimalField(
        _('قیمت خرید تکی (تومان)'),
        max_digits=10,
        decimal_places=0,
        default=0,
        validators=[MinValueValidator(0)],
    )
    requires_subscription = models.BooleanField(
        _('نیاز به اشتراک'),
        default=True,
        db_index=True,
        help_text=_('آیا با اشتراک فعال قابل دانلود است؟'),
    )
    view_count = models.PositiveIntegerField(_('تعداد بازدید'), default=0)
    created_at = models.DateTimeField(_('تاریخ ایجاد'), auto_now_add=True)
    updated_at = models.DateTimeField(_('آخرین به‌روزرسانی'), auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = _('شماتیک')
        verbose_name_plural = _('شماتیک‌ها')
        constraints = [
            models.UniqueConstraint(
                fields=['phone_model', 'category', 'title'],
                name='uniq_schematic_model_category_title',
            ),
            models.CheckConstraint(
                condition=models.Q(price__gte=0),
                name='schematic_price_non_negative',
            ),
        ]
        indexes = [
            models.Index(fields=['phone_model', 'category'], name='idx_schematic_model_cat'),
            models.Index(fields=['is_free', 'requires_subscription'], name='idx_schematic_access_flags'),
            models.Index(fields=['-created_at'], name='idx_schematic_created_desc'),
        ]

    def __str__(self) -> str:
        return f'{self.phone_model} - {self.title}'

    def user_can_download(self, user) -> bool:
        """
        Return whether `user` is allowed to stream this schematic's files.

        Anonymous users always get False; the download view additionally requires
        IsAuthenticated so JWT/session must be present before this matrix runs.

        Paid rows with `requires_subscription=False` are single-purchase-only
        (plus staff). That lets the catalog sell premium documents outside the
        subscription bundle.
        """
        if user is None or not getattr(user, 'is_authenticated', False):
            return False

        if self.is_free:
            return True

        if user.is_staff or user.is_superuser:
            return True

        # Single-copy entitlement (Phase 3 commerce writes these rows).
        if self.purchases.filter(user=user).exists():
            return True

        if self.requires_subscription:
            # Late import avoids a circular import with subscriptions.models.
            from subscriptions.models import UserSubscription

            return UserSubscription.objects.has_active_subscription(user)

        return False


class SchematicFile(models.Model):
    """
    One downloadable binary attached to a schematic (PDF boardview, ZIP of pages, ...).

    The FileField uses ProtectedSchematicStorage: `.url` is not a public MEDIA path.
    Clients must call SchematicFileDownloadView, which enforces `user_can_download`.
    """

    schematic = models.ForeignKey(
        Schematic,
        on_delete=models.CASCADE,
        related_name='files',
        verbose_name=_('شماتیک مربوطه'),
    )
    file = models.FileField(
        _('فایل نقشه / بردویو'),
        upload_to=schematic_file_upload_path,
        storage=protected_storage,
        validators=[
            FileExtensionValidator(allowed_extensions=['pdf', 'png', 'jpg', 'jpeg', 'zip']),
        ],
    )
    file_title = models.CharField(_('عنوان فایل'), max_length=150)
    file_size_bytes = models.BigIntegerField(_('حجم فایل (بایت)'), default=0, editable=False)
    created_at = models.DateTimeField(_('تاریخ آپلود'), auto_now_add=True)

    class Meta:
        verbose_name = _('فایل شماتیک')
        verbose_name_plural = _('فایل‌های شماتیک')
        ordering = ['id']
        indexes = [
            models.Index(fields=['schematic', '-created_at'], name='idx_schematicfile_parent'),
        ]

    def __str__(self) -> str:
        return f'{self.file_title} ({self.schematic.title})'

    def save(self, *args, **kwargs):
        # Cache size for API list payloads so we never stat the filesystem on every request.
        if self.file and hasattr(self.file, 'size'):
            try:
                self.file_size_bytes = self.file.size
            except (FileNotFoundError, OSError, ValueError):
                pass
        super().save(*args, **kwargs)


class SchematicPurchase(models.Model):
    """
    Ledger row proving a user paid for one schematic (single-copy purchase).

    UniqueConstraint(user, schematic) is the source of truth for "already bought"
    checks in `Schematic.user_can_download`. Do not rely on a separate index;
    the unique constraint already creates one.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='schematic_purchases',
        verbose_name=_('کاربر'),
    )
    schematic = models.ForeignKey(
        Schematic,
        on_delete=models.CASCADE,
        related_name='purchases',
        verbose_name=_('شماتیک خریداری‌شده'),
    )
    price_paid = models.DecimalField(
        _('مبلغ پرداخت‌شده (تومان)'),
        max_digits=10,
        decimal_places=0,
        validators=[MinValueValidator(0)],
    )
    created_at = models.DateTimeField(_('تاریخ خرید'), auto_now_add=True)

    class Meta:
        verbose_name = _('خرید تکی شماتیک')
        verbose_name_plural = _('خریدهای تکی شماتیک')
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'schematic'],
                name='uniq_schematic_purchase_user_schematic',
            ),
            models.CheckConstraint(
                condition=models.Q(price_paid__gte=0),
                name='schematic_purchase_price_non_negative',
            ),
        ]

    def __str__(self) -> str:
        return f'{self.user} - {self.schematic.title}'
