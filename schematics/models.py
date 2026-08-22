from django.db import models

import os
from django.conf import settings
from django.utils.text import slugify


def schematic_file_upload_path(instance, filename: str) -> str:
    """
    Generate dynamic upload path for schematic files partitioned by brand and model.
    """
    brand_name = instance.schematic.phone_model.brand.slug
    model_name = instance.schematic.phone_model.slug
    return f"schematics/{brand_name}/{model_name}/{filename}"


class Brand(models.Model):
    """
    Mobile brand entity (e.g., Apple, Samsung, Xiaomi).
    """
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True, allow_unicode=True)
    logo = models.ImageField(upload_to='brands/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Brand'
        verbose_name_plural = 'Brands'

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name, allow_unicode=True)
        super().save(*args, **kwargs)


class PhoneModel(models.Model):
    """
    Specific phone model belonging to a brand (e.g., iPhone 13 Pro, Galaxy S23 Ultra).
    """
    brand = models.ForeignKey(Brand, on_delete=models.CASCADE, related_name='phone_models')
    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=170, allow_unicode=True)
    technical_code = models.CharField(
        max_length=100, 
        blank=True, 
        help_text="Board or technical model code (e.g., SM-S918B, A2638)"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('brand', 'slug')
        ordering = ['brand', 'name']
        verbose_name = 'Phone Model'
        verbose_name_plural = 'Phone Models'

    def __str__(self) -> str:
        return f"{self.brand.name} - {self.name}"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name, allow_unicode=True)
        super().save(*args, **kwargs)


class SchematicCategory(models.Model):
    """
    Type of schematic or diagram (e.g., Full Schematic, BoardView, Hardware Solution, TestPoint).
    """
    title = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True, allow_unicode=True)
    description = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Schematic Category'
        verbose_name_plural = 'Schematic Categories'

    def __str__(self) -> str:
        return self.title


class Schematic(models.Model):
    """
    Core Schematic entity holding documentation, pricing, and access permissions.
    """
    phone_model = models.ForeignKey(PhoneModel, on_delete=models.CASCADE, related_name='schematics')
    category = models.ForeignKey(SchematicCategory, on_delete=models.PROTECT, related_name='schematics')
    title = models.CharField(max_length=255)
    description = models.TextField(
        blank=True,
        help_text="Detailed notes, repair technician tips, or troubleshooting guides."
    )
    is_free = models.BooleanField(
        default=False, 
        help_text="If checked, any registered user can download without payment."
    )
    price = models.DecimalField(
        max_digits=10, 
        decimal_places=0, 
        default=0, 
        help_text="Price for single purchase in Tomans (0 if free or subscription-only)."
    )
    requires_subscription = models.BooleanField(
        default=True,
        help_text="Whether this schematic is included in active subscription plans."
    )
    view_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Schematic'
        verbose_name_plural = 'Schematics'

    def __str__(self) -> str:
        return f"{self.phone_model} - {self.title}"


class SchematicFile(models.Model):
    """
    Attached downloadable files for a schematic (PDFs, BoardView archives, high-res images).
    """
    schematic = models.ForeignKey(Schematic, on_delete=models.CASCADE, related_name='files')
    file = models.FileField(upload_to=schematic_file_upload_path)
    file_title = models.CharField(max_length=150, help_text="e.g., Main Motherboard PDF, Sub-board Layout")
    file_size_bytes = models.BigIntegerField(default=0, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Schematic File'
        verbose_name_plural = 'Schematic Files'

    def __str__(self) -> str:
        return f"{self.file_title} ({self.schematic.title})"

    def save(self, *args, **kwargs):
        if self.file and hasattr(self.file, 'size'):
            self.file_size_bytes = self.file.size
        super().save(*args, **kwargs)
