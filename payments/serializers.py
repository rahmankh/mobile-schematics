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

    `purpose=schematic` needs schematic_id and/or schematic_ids.
    `purpose=wallet` needs amount. Subscription checkouts are retired.
    """

    purpose = serializers.ChoiceField(choices=CHECKOUT_PURPOSES)
    schematic_id = serializers.IntegerField(required=False)
    schematic_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_empty=False,
    )
    plan_id = serializers.IntegerField(required=False)
    amount = serializers.IntegerField(required=False, min_value=1)

    def validate(self, attrs):
        purpose = attrs['purpose']
        if purpose == PaymentTransaction.Purpose.SCHEMATIC:
            if not attrs.get('schematic_id') and not attrs.get('schematic_ids'):
                raise serializers.ValidationError(
                    {'schematic_ids': 'برای خرید شماتیک حداقل یک شناسه لازم است.'}
                )
        if purpose == PaymentTransaction.Purpose.WALLET and not attrs.get('amount'):
            raise serializers.ValidationError({'amount': 'برای شارژ کیف پول مبلغ لازم است.'})
        if purpose == PaymentTransaction.Purpose.SUBSCRIPTION:
            raise serializers.ValidationError(SUBSCRIPTION_RETIRED_MESSAGE)
        return attrs


class PaymentTransactionSerializer(serializers.ModelSerializer):
    """Public status of a payment session (never exposes gateway secrets)."""

    schematic_ids = serializers.SerializerMethodField()

    class Meta:
        model = PaymentTransaction
        fields = [
            'id',
            'purpose',
            'amount',
            'authority',
            'status',
            'schematic',
            'schematic_ids',
            'plan',
            'ref_id',
            'created_at',
            'verified_at',
        ]
        read_only_fields = fields

    def get_schematic_ids(self, obj) -> list[int]:
        return obj.purchased_schematic_ids()


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

