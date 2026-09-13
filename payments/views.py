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
    GuestClaimSerializer,
    PaymentRequestSerializer,
    PaymentTransactionSerializer,
)
from .services import (
    PaymentClaimDenied,
    PaymentConflict,
    PaymentError,
    claim_guest_session,
    create_payment_request,
    start_guest_schematic_checkout,
    verify_and_fulfill,
)


class PaymentRequestView(APIView):
    """
    POST /api/v1/payments/request/

    Body: {purpose: schematic|wallet, schematic_id?, schematic_ids?, amount?}
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
                schematic_ids=serializer.validated_data.get('schematic_ids'),
                plan_id=serializer.validated_data.get('plan_id'),
                amount=serializer.validated_data.get('amount'),
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

    Body: {phone_number, schematic_id}. Starts a PENDING schematic payment.
    Returns payment_url, authority, and a one-time claim_token. Does not
    report whether the phone already has an account.
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
            txn, payment_url, claim_token = start_guest_schematic_checkout(
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
        payload['claim_token'] = claim_token
        payload['detail'] = 'به درگاه پرداخت هدایت شوید.'
        return Response(payload, status=status.HTTP_201_CREATED)


class PaymentVerifyView(APIView):
    """
    GET /api/v1/payments/verify/?Authority=...&Status=OK

    Gateway callback. Authority proves the payment, not the account.
    This endpoint fulfills entitlements and never mints JWT.
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
        return Response(payload, status=status.HTTP_200_OK)


class PaymentClaimView(APIView):
    """
    POST /api/v1/payments/claim/

    Body: {authority, claim_token}. Issues JWT only when the token HMAC-matches
    a PAID transaction that created this guest account. Verify never mints JWT.
    """

    permission_classes = [AllowAny]
    throttle_classes = [GuestCheckoutRateThrottle]

    @extend_schema(tags=['payments'], request=GuestClaimSerializer)
    def post(self, request):
        serializer = GuestClaimSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            payload = claim_guest_session(
                authority=serializer.validated_data['authority'],
                claim_token=serializer.validated_data['claim_token'],
            )
        except PaymentClaimDenied as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except PaymentError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(payload, status=status.HTTP_200_OK)
