"""
Subscription catalog and checkout.

Plan listing and "my subscription" stay read-only. Purchase POSTs start a
payment session and must not insert UserSubscription until verify() succeeds.
"""

from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema

from payments.models import PaymentTransaction
from payments.serializers import PaymentTransactionSerializer
from payments.services import PaymentConflict, PaymentError, create_payment_request

from .models import Plan, UserSubscription
from .serializers import PlanSerializer, SubscribeRequestSerializer, UserSubscriptionSerializer


class PlanListAPIView(generics.ListAPIView):
    """GET active subscription SKUs."""

    queryset = Plan.objects.filter(is_active=True)
    serializer_class = PlanSerializer
    permission_classes = [AllowAny]


class CurrentUserSubscriptionAPIView(APIView):
    """GET the caller's currently valid subscription, if any."""

    permission_classes = [IsAuthenticated]

    @extend_schema(tags=['subscriptions'], responses=UserSubscriptionSerializer)
    def get(self, request):
        subscription = (
            UserSubscription.objects.filter(user=request.user)
            .select_related('plan')
            .active_subscriptions()
            .order_by('-end_date')
            .first()
        )
        if not subscription:
            return Response(
                {'detail': 'شما در حال حاضر هیچ اشتراک فعالی ندارید.', 'has_active_subscription': False},
                status=status.HTTP_200_OK,
            )
        data = UserSubscriptionSerializer(subscription).data
        data['has_active_subscription'] = True
        return Response(data, status=status.HTTP_200_OK)


class PurchaseSubscriptionAPIView(APIView):
    """
    POST /api/v1/subscriptions/purchase/

    Starts a payment for `plan_id`. Does **not** activate the plan; the client
    must complete GET /api/v1/payments/verify/ after the gateway redirect.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=['subscriptions'],
        request=SubscribeRequestSerializer,
        responses={201: PaymentTransactionSerializer},
    )
    def post(self, request):
        serializer = SubscribeRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            txn, payment_url = create_payment_request(
                user=request.user,
                purpose=PaymentTransaction.Purpose.SUBSCRIPTION,
                plan_id=serializer.validated_data['plan_id'],
                request=request,
            )
        except PaymentConflict as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_409_CONFLICT)
        except PaymentError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        payload = PaymentTransactionSerializer(txn).data
        payload['payment_url'] = payment_url
        payload['detail'] = 'به درگاه پرداخت هدایت شوید.'
        return Response(payload, status=status.HTTP_201_CREATED)
