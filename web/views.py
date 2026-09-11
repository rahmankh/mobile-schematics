"""
HTML catalog pages for technicians.

The JSON API under /api/v1/ stays untouched. These views render real pages
(brands, models, schematics) plus session login/logout in the site header.
"""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.db.models import Count, Prefetch
from django.shortcuts import get_object_or_404
from django.views.generic import DetailView, TemplateView

from schematics.models import Brand, PhoneModel, Schematic, SchematicCategory
from subscriptions.models import UserSubscription

from .forms import PhoneAuthenticationForm


class HomeView(TemplateView):
    """Landing page: brand grid, sample models, categories, and featured schematics."""

    template_name = 'web/home.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['brands'] = Brand.objects.annotate(
            models_count=Count('phone_models', distinct=True),
            schematics_count=Count('phone_models__schematics', distinct=True),
        ).order_by('name')
        context['categories'] = SchematicCategory.objects.annotate(
            schematics_count=Count('schematics'),
        )
        context['featured_schematics'] = (
            Schematic.objects.select_related(
                'phone_model__brand',
                'category',
            )
            .annotate(files_count=Count('files'))
            .order_by('-created_at')[:8]
        )
        # Sample devices so the dashboard is browsable without opening a brand first.
        context['sample_models'] = (
            PhoneModel.objects.select_related('brand')
            .annotate(schematics_count=Count('schematics'))
            .order_by('brand__name', 'name')[:12]
        )
        return context


class BrandDetailView(DetailView):
    """One manufacturer and every phone model under it."""

    model = Brand
    slug_field = 'slug'
    slug_url_kwarg = 'slug'
    template_name = 'web/brand_detail.html'
    context_object_name = 'brand'

    def get_queryset(self):
        return Brand.objects.prefetch_related(
            Prefetch(
                'phone_models',
                queryset=PhoneModel.objects.annotate(
                    schematics_count=Count('schematics'),
                ).order_by('name'),
            )
        )


class PhoneModelDetailView(TemplateView):
    """Schematics attached to one device (e.g. Galaxy S24 Ultra)."""

    template_name = 'web/model_detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        brand = get_object_or_404(Brand, slug=kwargs['brand_slug'])
        phone_model = get_object_or_404(
            PhoneModel.objects.select_related('brand'),
            brand=brand,
            slug=kwargs['model_slug'],
        )
        context['brand'] = brand
        context['phone_model'] = phone_model
        context['schematics'] = (
            Schematic.objects.filter(phone_model=phone_model)
            .select_related('category')
            .annotate(files_count=Count('files'))
            .order_by('category__title', 'title')
        )
        return context


class SchematicDetailPageView(DetailView):
    """Readable schematic page (notes + file list). Download still goes through the gated API."""

    model = Schematic
    template_name = 'web/schematic_detail.html'
    context_object_name = 'schematic'

    def get_queryset(self):
        return Schematic.objects.select_related(
            'phone_model__brand',
            'category',
        ).prefetch_related('files')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        schematic = context['schematic']
        user = self.request.user
        context['can_download'] = schematic.user_can_download(user) if user.is_authenticated else False
        return context


class TechnicianLoginView(LoginView):
    """Session login for the HTML UI. Mobile apps keep using JWT at /api/v1/accounts/login/."""

    template_name = 'web/login.html'
    authentication_form = PhoneAuthenticationForm
    redirect_authenticated_user = True


class TechnicianLogoutView(LogoutView):
    """POST-only logout so the header form cannot be triggered by a prefetch GET."""

    http_method_names = ['post', 'options']


class ProfilePageView(LoginRequiredMixin, TemplateView):
    """Technician identity + current subscription, used by the header profile link."""

    template_name = 'web/profile.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['subscription'] = (
            UserSubscription.objects.filter(user=self.request.user)
            .select_related('plan')
            .active_subscriptions()
            .order_by('-end_date')
            .first()
        )
        context['purchase_count'] = self.request.user.schematic_purchases.count()
        return context
