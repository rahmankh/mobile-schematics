import re
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

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
        cleaned_phone = value.strip()
        pattern = r'^(0|\+98)?9\d{9}$'
        if not re.match(pattern, cleaned_phone):
            raise serializers.ValidationError("شماره موبایل وارد شده معتبر نیست.")
        
        if cleaned_phone.startswith('+98'):
            cleaned_phone = '0' + cleaned_phone[3:]
        elif cleaned_phone.startswith('98'):
            cleaned_phone = '0' + cleaned_phone[2:]
        elif not cleaned_phone.startswith('0'):
            cleaned_phone = '0' + cleaned_phone

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
        return User.objects.create_user(password=password, **validated_data)


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        data['user'] = {
            'id': self.user.id,
            'phone_number': self.user.phone_number,
            'first_name': self.user.first_name,
            'last_name': self.user.last_name,
            'repair_shop_name': getattr(self.user, 'repair_shop_name', ''),
        }
        return data


class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            'id',
            'phone_number',
            'first_name',
            'last_name',
            'repair_shop_name',
            'date_joined',
        ]
        read_only_fields = ['id', 'phone_number', 'date_joined']