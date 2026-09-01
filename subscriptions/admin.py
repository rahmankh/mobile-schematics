
from django.contrib import admin
from .models import Plan, UserSubscription


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ('title', 'price', 'duration_days', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('title',)


@admin.register(UserSubscription)
class UserSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'plan', 'start_date', 'end_date', 'status', 'is_valid')
    list_filter = ('status', 'start_date', 'end_date')
    search_fields = ('user__phone_number', 'user__first_name', 'user__last_name', 'plan__title')
    raw_id_fields = ('user', 'plan')