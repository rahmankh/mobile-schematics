

from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.utils import timezone
from datetime import timedelta

from .models import Plan, UserSubscription
from .serializers import PlanSerializer, UserSubscriptionSerializer, SubscribeRequestSerializer


class PlanListAPIView(generics.ListAPIView):
    """مشاهده لیست پلن‌های فعال"""
    queryset = Plan.objects.filter(is_active=True)
    serializer_class = PlanSerializer
    permission_classes = [AllowAny]


class CurrentUserSubscriptionAPIView(APIView):
    """مشاهده وضعیت اشتراک فعلی کاربر لاگین‌شده"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        subscription = UserSubscription.objects.filter(
            user=request.user,
            status='active',
            end_date__gt=timezone.now()
        ).first()

        if not subscription:
            return Response(
                {"detail": "شما در حال حاضر هیچ اشتراک فعالی ندارید.", "has_active_subscription": False},
                status=status.HTTP_200_OK
            )

        serializer = UserSubscriptionSerializer(subscription)
        data = serializer.data
        data["has_active_subscription"] = True
        return Response(data, status=status.HTTP_200_OK)


class PurchaseSubscriptionAPIView(APIView):
    """
    خرید/فعال‌سازی اشتراک
    (در صورت فعال بودن اشتراک قبلی، تاریخ انقضا به انتهای اشتراک فعلی اضافه می‌شود)
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = SubscribeRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        plan = Plan.objects.get(id=serializer.validated_data['plan_id'])
        now = timezone.now()

        # بررسی وجود اشتراک فعال قبلی جهت محاسبه تمدید
        active_sub = UserSubscription.objects.filter(
            user=request.user,
            status='active',
            end_date__gt=now
        ).order_by('-end_date').first()

        start_date = active_sub.end_date if active_sub else now
        end_date = start_date + timedelta(days=plan.duration_days)

        new_subscription = UserSubscription.objects.create(
            user=request.user,
            plan=plan,
            start_date=start_date,
            end_date=end_date,
            status='active'
        )

        return Response(
            {
                "detail": "اشتراک شما با موفقیت فعال شد.",
                "subscription": UserSubscriptionSerializer(new_subscription).data
            },
            status=status.HTTP_201_CREATED
        )