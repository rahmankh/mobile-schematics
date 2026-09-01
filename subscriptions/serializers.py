

from rest_framework import serializers
from django.utils import timezone
from datetime import timedelta
from .models import Plan, UserSubscription


class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = ('id', 'title', 'description', 'price', 'duration_days', 'is_active')


class UserSubscriptionSerializer(serializers.ModelSerializer):
    plan_title = serializers.CharField(source='plan.title', read_only=True)
    is_valid = serializers.BooleanField(read_only=True)

    class Meta:
        model = UserSubscription
        fields = ('id', 'plan', 'plan_title', 'start_date', 'end_date', 'status', 'is_valid', 'created_at')
        read_only_fields = ('start_date', 'end_date', 'status', 'created_at')


class SubscribeRequestSerializer(serializers.Serializer):
    plan_id = serializers.IntegerField(required=True)

    def validate_plan_id(self, value):
        try:
            plan = Plan.objects.get(id=value, is_active=True)
        except Plan.DoesNotExist:
            raise serializers.ValidationError("پلن انتخابی معتبر یا فعال نیست.")
        return value