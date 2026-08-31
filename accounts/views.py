from django.shortcuts import render

# Create your views here.
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView
from django.contrib.auth import get_user_model

from .serializers import (
    TechnicianRegisterSerializer,
    CustomTokenObtainPairSerializer,
    UserProfileSerializer,
)

User = get_user_model()


class RegisterView(generics.CreateAPIView):
    """
    ثبت‌نام تکنسین جدید
    """
    queryset = User.objects.all()
    serializer_class = TechnicianRegisterSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            {
                "message": "ثبت‌نام با موفقیت انجام شد.",
                "user": {
                    "id": user.id,
                    "phone_number": user.phone_number,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                }
            },
            status=status.HTTP_201_CREATED
        )


class CustomLoginView(TokenObtainPairView):
    """
    ورود و دریافت توکن JWT
    """
    serializer_class = CustomTokenObtainPairSerializer
    permission_classes = [AllowAny]


class ProfileView(generics.RetrieveUpdateAPIView):
    """
    مشاهده و ویرایش پروفایل کاربری تکنسین
    """
    serializer_class = UserProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user