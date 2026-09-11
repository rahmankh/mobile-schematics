"""
HTTP endpoints for gateway checkout.

POST /request/  — authenticated; creates PENDING PaymentTransaction only.
GET  /verify/   — gateway callback (no JWT); fulfills entitlements only on success.
"""

from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema

from config.throttling import GuestCheckoutRateThrottle

from .models import PaymentTransaction
from .serializers import (
    GuestCheckoutSerializer,
    PaymentRequestSerializer,
    PaymentTransactionSerializer,
)
from .services import (
    PaymentConflict,
    PaymentError,
    create_payment_request,
    start_guest_schematic_checkout,
    verify_access_payload,
    verify_and_fulfill,
)


class PaymentRequestView(APIView):
    """
    POST /api/v1/payments/request/

    Body: {purpose: schematic|subscription, schematic_id? , plan_id?}
    Returns authority + payment_url. Does not unlock content.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=['payments'],
        request=PaymentRequestSerializer,
        responses={201: PaymentTransactionSerializer},
    )
    def post(self, request):
        serializer = PaymentRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            txn, payment_url = create_payment_request(
                user=request.user,
                purpose=serializer.validated_data['purpose'],
                schematic_id=serializer.validated_data.get('schematic_id'),
                plan_id=serializer.validated_data.get('plan_id'),
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


class GuestCheckoutView(APIView):
    """
    POST /api/v1/payments/guest/

    Body: {phone_number, schematic_id}. Creates/reuses the account for that
    mobile number and starts a PENDING schematic payment. No password required.
    """

    permission_classes = [AllowAny]
    throttle_classes = [GuestCheckoutRateThrottle]

    @extend_schema(
        tags=['payments'],
        request=GuestCheckoutSerializer,
        responses={201: PaymentTransactionSerializer},
    )
    def post(self, request):
        serializer = GuestCheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            txn, payment_url, account_status = start_guest_schematic_checkout(
                phone_number=serializer.validated_data['phone_number'],
                schematic_id=serializer.validated_data['schematic_id'],
                request=request,
            )
        except PaymentConflict as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_409_CONFLICT)
        except PaymentError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        payload = PaymentTransactionSerializer(txn).data
        payload['payment_url'] = payment_url
        payload['account_status'] = account_status
        payload['detail'] = 'به درگاه پرداخت هدایت شوید.'
        return Response(payload, status=status.HTTP_201_CREATED)


class PaymentVerifyView(APIView):
    """
    GET /api/v1/payments/verify/?Authority=...&Status=OK

    Zarinpal-style query params. Authority is the capability token, so this
    endpoint is AllowAny. Failed or canceled payments never call fulfill().
    """

    permission_classes = [AllowAny]

    @extend_schema(
        tags=['payments'],
        responses={200: PaymentTransactionSerializer},
    )
    def get(self, request):
        authority = request.query_params.get('Authority') or request.query_params.get('authority')
        raw_status = (request.query_params.get('Status') or request.query_params.get('status') or '')
        if not authority:
            return Response(
                {'detail': 'پارامتر Authority الزامی است.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        gateway_ok = raw_status.upper() in ('OK', 'SUCCESS', '')
        # Empty Status is treated as OK so mobile clients can poll with authority only.
        if raw_status.upper() in ('NOK', 'FAILED', 'CANCELED', 'CANCELLED'):
            gateway_ok = False

        try:
            txn = verify_and_fulfill(authority=authority, gateway_ok=gateway_ok)
        except PaymentError as exc:
            return Response({'detail': str(exc), 'paid': False}, status=status.HTTP_400_BAD_REQUEST)

        payload = PaymentTransactionSerializer(txn).data
        payload['paid'] = txn.status == PaymentTransaction.Status.PAID
        payload['detail'] = 'پرداخت با موفقیت تایید شد.' if payload['paid'] else 'پرداخت تایید نشد.'
        if payload['paid']:
            payload.update(verify_access_payload(txn.user))
        return Response(payload, status=status.HTTP_200_OK)
