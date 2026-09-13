"""DRF serializers for starting a payment session."""

from rest_framework import serializers

from rest_framework.exceptions import ValidationError as DRFValidationError

from accounts.phone import normalize_iranian_phone
from payments.models import PaymentTransaction
from payments.services import SUBSCRIPTION_RETIRED_MESSAGE

CHECKOUT_PURPOSES = (
    PaymentTransaction.Purpose.SCHEMATIC,
    PaymentTransaction.Purpose.WALLET,
)


class PaymentRequestSerializer(serializers.Serializer):
    """
    Cart payload.

    `purpose=schematic` needs schematic_id. `purpose=wallet` needs amount.
    Subscription checkouts are retired.
    """

    purpose = serializers.ChoiceField(choices=CHECKOUT_PURPOSES)
    schematic_id = serializers.IntegerField(required=False)
    plan_id = serializers.IntegerField(required=False)
    amount = serializers.IntegerField(required=False, min_value=1)

    def validate(self, attrs):
        purpose = attrs['purpose']
        if purpose == PaymentTransaction.Purpose.SCHEMATIC and not attrs.get('schematic_id'):
            raise serializers.ValidationError({'schematic_id': 'برای خرید تکی شماتیک لازم است.'})
        if purpose == PaymentTransaction.Purpose.WALLET and not attrs.get('amount'):
            raise serializers.ValidationError({'amount': 'برای شارژ کیف پول مبلغ لازم است.'})
        if purpose == PaymentTransaction.Purpose.SUBSCRIPTION:
            raise serializers.ValidationError(SUBSCRIPTION_RETIRED_MESSAGE)
        return attrs


class PaymentTransactionSerializer(serializers.ModelSerializer):
    """Public status of a payment session (never exposes gateway secrets)."""

    class Meta:
        model = PaymentTransaction
        fields = [
            'id',
            'purpose',
            'amount',
            'authority',
            'status',
            'schematic',
            'plan',
            'ref_id',
            'created_at',
            'verified_at',
        ]
        read_only_fields = fields


class GuestCheckoutSerializer(serializers.Serializer):
    """
    Unauthenticated single-schematic checkout.

    Only a phone number and schematic id are required — no password.
    """

    phone_number = serializers.CharField()
    schematic_id = serializers.IntegerField()

    def validate_phone_number(self, value: str) -> str:
        try:
            return normalize_iranian_phone(value)
        except DRFValidationError as exc:
            raise serializers.ValidationError(exc.detail) from exc


class GuestClaimSerializer(serializers.Serializer):
    """Prove possession of the checkout-bound claim token after verify()."""

    authority = serializers.CharField()
    claim_token = serializers.CharField()

