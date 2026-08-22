import os
from django.db import models
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _


def schematic_file_upload_path(instance, filename: str) -> str:
    brand_name = instance.schematic.phone_model.brand.slug
    model_name = instance.schematic.phone_model.slug
    return f"schematics/{brand_name}/{model_name}/{filename}"


class Brand(models.Model):
    name = models.CharField(_('Brand Name'), max_length=100, unique=True)
    slug = models.SlugField(_('Slug'), max_length=120, unique=True, allow_unicode=True)
    logo = models.ImageField(_('Logo'), upload_to='brands/', blank=True, null=True)
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name = _('Brand')
        verbose_name_plural = _('Brands')

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name, allow_unicode=True)
        super().save(*args, **kwargs)


class PhoneModel(models.Model):
    brand = models.ForeignKey(Brand, on_delete=models.CASCADE, related_name='phone_models', verbose_name=_('Brand'))
    name = models.CharField(_('Model Name'), max_length=150)
    slug = models.SlugField(_('Slug'), max_length=170, allow_unicode=True)
    technical_code = models.CharField(
        _('Technical / Board Code'),
        max_length=100,
        blank=True,
        help_text=_("e.g., SM-S918B, A2638")
    )
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)

    class Meta:
        unique_together = ('brand', 'slug')
        ordering = ['brand', 'name']
        verbose_name = _('Phone Model')
        verbose_name_plural = _('Phone Models')

    def __str__(self) -> str:
        return f"{self.brand.name} - {self.name}"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name, allow_unicode=True)
        super().save(*args, **kwargs)


class SchematicCategory(models.Model):
    title = models.CharField(_('Category Title'), max_length=100, unique=True)
    slug = models.SlugField(_('Slug'), max_length=120, unique=True, allow_unicode=True)
    description = models.TextField(_('Description'), blank=True)

    class Meta:
        verbose_name = _('Schematic Category')
        verbose_name_plural = _('Schematic Categories')

    def __str__(self) -> str:
        return self.title


class Schematic(models.Model):
    phone_model = models.ForeignKey(PhoneModel, on_delete=models.CASCADE, related_name='schematics', verbose_name=_('Phone Model'))
    category = models.ForeignKey(SchematicCategory, on_delete=models.PROTECT, related_name='schematics', verbose_name=_('Category'))
    title = models.CharField(_('Schematic Title'), max_length=255)
    description = models.TextField(
        _('Technical Notes & Solutions'),
        blank=True,
        help_text=_("Detailed notes, repair technician tips, or troubleshooting guides.")
    )
    is_free = models.BooleanField(
        _('Is Free'),
        default=False,
        help_text=_("If checked, any registered user can download without payment.")
    )
    price = models.DecimalField(
        _('Single Purchase Price (Tomans)'),
        max_digits=10,
        decimal_places=0,
        default=0
    )
    requires_subscription = models.BooleanField(
        _('Requires Subscription'),
        default=True,
        help_text=_("Whether this schematic is included in active subscription plans.")
    )
    view_count = models.PositiveIntegerField(_('View Count'), default=0)
    created_at = models.DateTimeField(_('Created At'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Updated At'), auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = _('Schematic')
        verbose_name_plural = _('Schematics')

    def __str__(self) -> str:
        return f"{self.phone_model} - {self.title}"


class SchematicFile(models.Model):
    schematic = models.ForeignKey(Schematic, on_delete=models.CASCADE, related_name='files', verbose_name=_('Schematic'))
    file = models.FileField(_('File'), upload_to=schematic_file_upload_path)
    file_title = models.CharField(_('File Title'), max_length=150)
    file_size_bytes = models.BigIntegerField(_('File Size (Bytes)'), default=0, editable=False)
    created_at = models.DateTimeField(_('Upload Date'), auto_now_add=True)

    class Meta:
        verbose_name = _('Schematic File')
        verbose_name_plural = _('Schematic Files')

    def __str__(self) -> str:
        return f"{self.file_title} ({self.schematic.title})"

    def save(self, *args, **kwargs):
        if self.file and hasattr(self.file, 'size'):
            self.file_size_bytes = self.file.size
        super().save(*args, **kwargs)