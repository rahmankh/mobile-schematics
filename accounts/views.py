from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenBlacklistView, TokenObtainPairView, TokenRefreshView
from django.contrib.auth import get_user_model
from django.db.models import Prefetch
from drf_spectacular.utils import extend_schema

from accounts.services import issue_jwt_for, public_account_payload
from config.throttling import LoginRateThrottle
from schematics.models import SchematicPurchase
from subscriptions.models import UserSubscription

from .serializers import (
    CustomTokenObtainPairSerializer,
    SetPasswordSerializer,
    TechnicianRegisterSerializer,
    UserProfileSerializer,
)

User = get_user_model()


class RegisterView(generics.CreateAPIView):
    """
    POST /api/v1/accounts/register/

    Creates a regular technician (never staff/admin), hashes the password, and
    returns a signed JWT pair so the client can hit profile without a second login.
    """

    queryset = User.objects.all()
    serializer_class = TechnicianRegisterSerializer
    permission_classes = [AllowAny]
    throttle_classes = [LoginRateThrottle]

    @extend_schema(tags=['accounts'])
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        payload = {
            'message': 'ثبت‌نام با موفقیت انجام شد.',
            'user': public_account_payload(user),
        }
        payload.update(issue_jwt_for(user))
        return Response(payload, status=status.HTTP_201_CREATED)


class CustomLoginView(TokenObtainPairView):
    """
    ورود و دریافت توکن JWT
    """
    serializer_class = CustomTokenObtainPairSerializer
    permission_classes = [AllowAny]
    throttle_classes = [LoginRateThrottle]

    @extend_schema(tags=['accounts'])
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


class CustomTokenRefreshView(TokenRefreshView):
    """Rotate refresh tokens and blacklist the previous jti. Shares the login IP budget."""

    permission_classes = [AllowAny]
    throttle_classes = [LoginRateThrottle]


class LogoutView(TokenBlacklistView):
    """
    POST /api/v1/accounts/logout/

    Body: {refresh: <token>}. Blacklists that refresh jti so it cannot mint
    another access token. Access tokens already issued expire on their own TTL.
    """

    permission_classes = [AllowAny]
    throttle_classes = [LoginRateThrottle]

    @extend_schema(tags=['accounts'])
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


class ProfileView(generics.RetrieveUpdateAPIView):
    """
    GET/PATCH /api/v1/accounts/profile/

    Dashboard: phone, shop name, current subscription, and owned schematics.
    """

    serializer_class = UserProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        user = (
            User.objects.prefetch_related(
                Prefetch(
                    'schematic_purchases',
                    queryset=SchematicPurchase.objects.select_related(
                        'schematic',
                        'schematic__phone_model__brand',
                    ).order_by('-created_at'),
                )
            ).get(pk=self.request.user.pk)
        )
        user._active_subscription = (
            UserSubscription.objects.filter(user=user)
            .select_related('plan')
            .active_subscriptions()
            .order_by('-end_date')
            .first()
        )
        return user


class SetPasswordView(APIView):
    """
    POST /api/v1/accounts/set-password/

    Guests (unusable password) set a login password after paying. Registered
    technicians are rejected so this cannot be used as an unauthenticated reset.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(tags=['accounts'], request=SetPasswordSerializer, responses={200: None})
    def post(self, request):
        if not request.user.is_guest:
            return Response(
                {'detail': 'این حساب از قبل رمز عبور دارد. از ورود معمولی استفاده کنید.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = SetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data['password'])
        request.user.save(update_fields=['password'])
        return Response(
            {'detail': 'رمز عبور با موفقیت تنظیم شد. از این پس می‌توانید وارد شوید.'},
            status=status.HTTP_200_OK,
        )
