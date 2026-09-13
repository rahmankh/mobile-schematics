"""
HTML catalog pages for the web UI.

The JSON API under /api/v1/ stays untouched. These views render real pages
(brands, models, schematics) plus session login/logout in the site header.
"""

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count, Prefetch, Q, Sum
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import DetailView, FormView, TemplateView

from accounts.password_reset import CONFIRM_SUCCESS_MESSAGE, GENERIC_REQUEST_MESSAGE
from payments.services import PaymentConflict, PaymentError, create_payment_request, pay_schematic_from_wallet
from schematics.models import Brand, PhoneModel, Schematic, SchematicCategory, SchematicPurchase

from .cart import add_to_cart, clear_cart, get_cart_ids, remove_from_cart

from .forms import (
    PasswordResetConfirmForm,
    PasswordResetRequestForm,
    PhoneAuthenticationForm,
    TechnicianRegisterForm,
)


class HomeView(TemplateView):
    """Landing page: brand grid, sample models, categories, and featured schematics."""

    template_name = 'web/home.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        query = (self.request.GET.get('q') or '').strip()
        access = (self.request.GET.get('access') or '').strip()
        category_slug = (self.request.GET.get('category') or '').strip()
        is_filtered = bool(query or access or category_slug)

        brands = Brand.objects.annotate(
            models_count=Count('phone_models', distinct=True),
            schematics_count=Count('phone_models__schematics', distinct=True),
        ).order_by('name')
        if query:
            brands = brands.filter(
                Q(name__icontains=query) | Q(phone_models__name__icontains=query)
            ).distinct()

        categories = SchematicCategory.objects.annotate(
            schematics_count=Count('schematics'),
        )
        sample_models = (
            PhoneModel.objects.select_related('brand')
            .annotate(schematics_count=Count('schematics'))
            .order_by('brand__name', 'name')
        )
        if query:
            sample_models = sample_models.filter(
                Q(name__icontains=query)
                | Q(technical_code__icontains=query)
                | Q(brand__name__icontains=query)
            )

        schematics = (
            Schematic.objects.select_related(
                'phone_model__brand',
                'category',
            )
            .annotate(
                files_count=Count('files'),
                total_size=Sum('files__file_size_bytes'),
            )
            .order_by('-created_at')
        )
        if query:
            schematics = schematics.filter(
                Q(title__icontains=query)
                | Q(description__icontains=query)
                | Q(phone_model__name__icontains=query)
                | Q(phone_model__technical_code__icontains=query)
                | Q(phone_model__brand__name__icontains=query)
            )
        if access == 'free':
            schematics = schematics.filter(is_free=True)
        elif access == 'paid':
            schematics = schematics.filter(is_free=False)
        if category_slug:
            schematics = schematics.filter(category__slug=category_slug)

        context['catalog_query'] = query
        context['catalog_access'] = access
        context['catalog_category'] = category_slug
        context['is_filtered'] = is_filtered
        context['brands'] = brands
        context['categories'] = categories
        context['sample_models'] = sample_models[:12]
        context['featured_schematics'] = schematics[:50] if is_filtered else schematics[:8]
        context['schematic_results_count'] = schematics.count() if is_filtered else None
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
            .select_related('category', 'phone_model__brand')
            .annotate(
                files_count=Count('files'),
                total_size=Sum('files__file_size_bytes'),
            )
            .order_by('category__title', 'title')
        )
        return context


class SchematicDetailPageView(DetailView):
    """Readable schematic page. Entitled users get the in-browser viewer, not a raw download."""

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
        can_view = schematic.user_can_view(user) if user.is_authenticated else False
        wallet_balance = getattr(user, 'wallet_balance', 0) if user.is_authenticated else 0
        context['can_view'] = can_view
        context['can_download'] = False
        context['viewer_watermark'] = ''
        if user.is_authenticated:
            context['viewer_watermark'] = ' · '.join(
                part for part in (user.get_full_name(), user.phone_number) if part
            )
        context['can_wallet_pay'] = (
            user.is_authenticated
            and not can_view
            and not schematic.is_free
            and schematic.price > 0
            and wallet_balance >= schematic.price
        )
        return context


class TechnicianLoginView(LoginView):
    """Session login for the HTML UI. Mobile apps keep using JWT at /api/v1/accounts/login/."""

    template_name = 'web/login.html'
    authentication_form = PhoneAuthenticationForm
    redirect_authenticated_user = True


class TechnicianRegisterView(FormView):
    """
    HTML signup for technicians. Creates the same non-admin account as
    POST /api/v1/accounts/register/, then starts a Django session (not JWT).
    """

    template_name = 'web/register.html'
    form_class = TechnicianRegisterForm
    success_url = reverse_lazy('web:home')

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect(self.get_success_url())
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        user = form.save()
        login(self.request, user, backend='django.contrib.auth.backends.ModelBackend')
        return super().form_valid(form)


class PasswordResetRequestView(FormView):
    """HTML step 1. Always continues to confirm so phone existence is not leaked."""

    template_name = 'web/password_reset.html'
    form_class = PasswordResetRequestForm

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('web:home')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.send()
        messages.success(self.request, GENERIC_REQUEST_MESSAGE)
        phone = form.cleaned_data['phone_number']
        return redirect(f"{reverse('web:password-reset-confirm')}?phone={phone}")


class PasswordResetConfirmView(FormView):
    """HTML step 2. Sets the password then sends the technician to login."""

    template_name = 'web/password_reset_confirm.html'
    form_class = PasswordResetConfirmForm
    success_url = reverse_lazy('web:login')

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('web:home')
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        initial = super().get_initial()
        phone = self.request.GET.get('phone', '')
        if phone:
            initial['phone_number'] = phone
        return initial

    def form_valid(self, form):
        try:
            form.save()
        except DjangoValidationError as exc:
            form.add_error(None, exc.messages)
            return self.form_invalid(form)
        messages.success(self.request, CONFIRM_SUCCESS_MESSAGE)
        return super().form_valid(form)


class TechnicianLogoutView(LogoutView):
    """POST-only logout so the header form cannot be triggered by a prefetch GET."""

    http_method_names = ['post', 'options']


class ProfilePageView(LoginRequiredMixin, TemplateView):
    """Account identity, wallet balance, and single-copy purchases."""

    template_name = 'web/profile.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['purchase_count'] = self.request.user.schematic_purchases.count()
        return context


class SchematicCheckoutView(LoginRequiredMixin, View):
    """Start a gateway session for a single schematic purchase."""

    http_method_names = ['post']

    def post(self, request, pk):
        try:
            _txn, payment_url = create_payment_request(
                user=request.user,
                purpose='schematic',
                schematic_id=pk,
                request=request,
            )
        except PaymentConflict as exc:
            messages.error(request, str(exc))
            return redirect('web:schematic-detail', pk=pk)
        except PaymentError as exc:
            messages.error(request, str(exc))
            return redirect('web:schematic-detail', pk=pk)
        return redirect(payment_url)


class CartAddView(View):
    """Append a schematic to the session cart without starting payment."""

    http_method_names = ['post']

    def post(self, request, pk):
        schematic = get_object_or_404(Schematic, pk=pk)
        next_url = request.POST.get('next') or reverse('web:cart')
        if schematic.is_free or schematic.price <= 0:
            messages.error(request, 'این شماتیک برای خرید تکی در دسترس نیست.')
            return redirect(next_url)
        if (
            request.user.is_authenticated
            and SchematicPurchase.objects.filter(user=request.user, schematic=schematic).exists()
        ):
            messages.error(request, 'این شماتیک را قبلاً خریداری کرده‌اید.')
            return redirect(next_url)
        add_to_cart(request, schematic.pk)
        messages.success(request, 'به سبد خرید اضافه شد.')
        return redirect(next_url)


class CartRemoveView(View):
    """Drop one schematic from the session cart."""

    http_method_names = ['post']

    def post(self, request, pk):
        remove_from_cart(request, pk)
        messages.success(request, 'از سبد خرید حذف شد.')
        next_url = request.POST.get('next') or reverse('web:cart')
        return redirect(next_url)


class CartPageView(TemplateView):
    """Session cart: line items, aggregate total, and batch checkout."""

    template_name = 'web/cart.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        ids = get_cart_ids(self.request)
        items = list(
            Schematic.objects.filter(pk__in=ids)
            .select_related('phone_model__brand', 'category')
        )
        by_id = {item.pk: item for item in items}
        ordered = [by_id[pk] for pk in ids if pk in by_id]
        owned_ids: set[int] = set()
        if self.request.user.is_authenticated and ordered:
            owned_ids = set(
                SchematicPurchase.objects.filter(
                    user=self.request.user,
                    schematic_id__in=[item.pk for item in ordered],
                ).values_list('schematic_id', flat=True)
            )
        payable = [
            item
            for item in ordered
            if not item.is_free and item.price > 0 and item.pk not in owned_ids
        ]
        context['cart_items'] = ordered
        context['cart_owned_ids'] = owned_ids
        context['cart_payable'] = payable
        context['cart_total'] = sum((item.price for item in payable), 0)
        return context


class CartCheckoutView(LoginRequiredMixin, View):
    """Start one gateway session for every payable schematic in the cart."""

    http_method_names = ['post']

    def post(self, request):
        ids = get_cart_ids(request)
        if not ids:
            messages.error(request, 'سبد خرید خالی است.')
            return redirect('web:cart')
        try:
            _txn, payment_url = create_payment_request(
                user=request.user,
                purpose='schematic',
                schematic_ids=ids,
                request=request,
            )
        except PaymentConflict as exc:
            messages.error(request, str(exc))
            return redirect('web:cart')
        except PaymentError as exc:
            messages.error(request, str(exc))
            return redirect('web:cart')
        clear_cart(request)
        return redirect(payment_url)


class WalletPaySchematicView(LoginRequiredMixin, View):
    """Spend wallet balance on one schematic."""

    http_method_names = ['post']

    def post(self, request, pk):
        try:
            pay_schematic_from_wallet(request.user, pk)
        except PaymentConflict as exc:
            messages.error(request, str(exc))
        except PaymentError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, 'خرید با کیف پول انجام شد.')
        return redirect('web:schematic-detail', pk=pk)


class WalletTopUpView(LoginRequiredMixin, View):
    """Start a gateway session that credits the user's wallet after verify."""

    http_method_names = ['post']

    def post(self, request):
        try:
            _txn, payment_url = create_payment_request(
                user=request.user,
                purpose='wallet',
                amount=request.POST.get('amount'),
                request=request,
            )
        except PaymentError as exc:
            messages.error(request, str(exc))
            return redirect('web:profile')
        return redirect(payment_url)
