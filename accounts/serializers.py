from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework.exceptions import ValidationError as DRFValidationError
from drf_spectacular.utils import extend_schema_field

from accounts.phone import normalize_iranian_phone
from accounts.services import public_account_payload
from schematics.serializers import SchematicPurchaseSerializer
from subscriptions.serializers import UserSubscriptionSerializer

User = get_user_model()


class TechnicianRegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True,
        required=True,
        validators=[validate_password],
        style={'input_type': 'password'}
    )
    password_confirm = serializers.CharField(
        write_only=True,
        required=True,
        style={'input_type': 'password'}
    )

    class Meta:
        model = User
        fields = [
            'phone_number',
            'first_name',
            'last_name',
            'repair_shop_name',
            'password',
            'password_confirm',
        ]

    def validate_phone_number(self, value: str) -> str:
        try:
            cleaned_phone = normalize_iranian_phone(value)
        except DRFValidationError as exc:
            raise serializers.ValidationError(exc.detail) from exc

        if User.objects.filter(phone_number=cleaned_phone).exists():
            raise serializers.ValidationError("کاربری با این شماره موبایل قبلاً ثبت‌نام کرده است.")

        return cleaned_phone

    def validate(self, attrs: dict) -> dict:
        if attrs.get('password') != attrs.get('password_confirm'):
            raise serializers.ValidationError({"password_confirm": "رمزهای عبور وارد شده یکسان نیستند."})
        return attrs

    def create(self, validated_data: dict):
        validated_data.pop('password_confirm')
        password = validated_data.pop('password')
        # Privilege fields are not in Meta.fields; strip them anyway so a future
        # serializer change cannot turn public register into an admin factory.
        for privileged in (
            'role',
            'is_staff',
            'is_superuser',
            'is_active',
            'groups',
            'user_permissions',
        ):
            validated_data.pop(privileged, None)
        return User.objects.create_user(
            password=password,
            role=User.RoleChoices.TECHNICIAN,
            is_staff=False,
            is_superuser=False,
            **validated_data,
        )


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """JWT login. Phone is normalized so +98 and 09 forms hit the same row."""

    def validate(self, attrs):
        raw = attrs.get(self.username_field)
        try:
            attrs[self.username_field] = normalize_iranian_phone(raw)
        except DRFValidationError as exc:
            raise serializers.ValidationError({self.username_field: exc.detail}) from exc
        data = super().validate(attrs)
        data['user'] = public_account_payload(self.user)
        return data


class UserProfileSerializer(serializers.ModelSerializer):
    """
    Status dashboard: identity plus the caller's live entitlement snapshot.

    `subscription` / `purchases` are read-only; commerce writes happen in payments.
    """

    is_guest = serializers.BooleanField(read_only=True)
    has_active_subscription = serializers.SerializerMethodField()
    subscription = serializers.SerializerMethodField()
    purchases = serializers.SerializerMethodField()
    purchase_count = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id',
            'phone_number',
            'first_name',
            'last_name',
            'repair_shop_name',
            'date_joined',
            'is_guest',
            'has_active_subscription',
            'subscription',
            'purchases',
            'purchase_count',
        ]
        read_only_fields = [
            'id',
            'phone_number',
            'date_joined',
            'is_guest',
            'has_active_subscription',
            'subscription',
            'purchases',
            'purchase_count',
        ]

    def _active_subscription(self, obj):
        if hasattr(obj, '_active_subscription'):
            return obj._active_subscription
        from subscriptions.models import UserSubscription

        return (
            UserSubscription.objects.filter(user=obj)
            .select_related('plan')
            .active_subscriptions()
            .order_by('-end_date')
            .first()
        )

    def get_has_active_subscription(self, obj) -> bool:
        return self._active_subscription(obj) is not None

    @extend_schema_field(UserSubscriptionSerializer)
    def get_subscription(self, obj):
        sub = self._active_subscription(obj)
        if not sub:
            return None
        return UserSubscriptionSerializer(sub).data

    @extend_schema_field(SchematicPurchaseSerializer(many=True))
    def get_purchases(self, obj):
        qs = obj.schematic_purchases.select_related(
            'schematic',
            'schematic__phone_model__brand',
        ).order_by('-created_at')
        return SchematicPurchaseSerializer(qs, many=True).data

    def get_purchase_count(self, obj) -> int:
        # Uses the prefetch cache when ProfileView prefetched schematic_purchases.
        return obj.schematic_purchases.count()


class SetPasswordSerializer(serializers.Serializer):
    """Upgrade a guest (unusable password) into a password-login technician."""

    password = serializers.CharField(
        write_only=True,
        required=True,
        validators=[validate_password],
        style={'input_type': 'password'},
    )
    password_confirm = serializers.CharField(
        write_only=True,
        required=True,
        style={'input_type': 'password'},
    )

    def validate(self, attrs: dict) -> dict:
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError(
                {'password_confirm': 'رمزهای عبور وارد شده یکسان نیستند.'}
            )
        return attrs


class PasswordResetRequestSerializer(serializers.Serializer):
    """Start a reset. Response is always the same so phone existence is not leaked."""

    phone_number = serializers.CharField()

    def validate_phone_number(self, value: str) -> str:
        try:
            return normalize_iranian_phone(value)
        except DRFValidationError as exc:
            raise serializers.ValidationError(exc.detail) from exc


class PasswordResetConfirmSerializer(serializers.Serializer):
    """Verify the OTP and set a new hashed password. Does not return JWT."""

    phone_number = serializers.CharField()
    otp = serializers.CharField(write_only=True, max_length=16)
    password = serializers.CharField(
        write_only=True,
        required=True,
        validators=[validate_password],
        style={'input_type': 'password'},
    )
    password_confirm = serializers.CharField(
        write_only=True,
        required=True,
        style={'input_type': 'password'},
    )

    def validate_phone_number(self, value: str) -> str:
        try:
            return normalize_iranian_phone(value)
        except DRFValidationError as exc:
            raise serializers.ValidationError(exc.detail) from exc

    def validate_otp(self, value: str) -> str:
        return str(value or '').strip()

    def validate(self, attrs: dict) -> dict:
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError(
                {'password_confirm': 'رمزهای عبور وارد شده یکسان نیستند.'}
            )
        return attrs
