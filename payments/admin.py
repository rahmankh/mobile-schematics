"""Admin for payment intents. Entitlements are granted only when status=paid."""

from django.contrib import admin

from .models import PaymentTransaction


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    """Support search by authority / phone. Status filter is the main ops view."""

    list_display = (
        'authority',
        'user',
        'purpose',
        'amount',
        'status',
        'gateway',
        'ref_id',
        'created_at',
        'verified_at',
    )
    list_filter = ('status', 'purpose', 'gateway', 'created_at')
    search_fields = ('authority', 'ref_id', 'user__phone_number', 'description')
    raw_id_fields = ('user', 'schematic', 'plan')
    readonly_fields = (
        'authority',
        'ref_id',
        'created_at',
        'verified_at',
        'gateway',
        'claim_token_hash',
        'guest_account_created',
        'claimed_at',
    )
    date_hierarchy = 'created_at'
