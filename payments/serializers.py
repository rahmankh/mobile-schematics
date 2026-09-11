"""DRF serializers for starting a payment session."""

from rest_framework import serializers

from .models import PaymentTransaction


class PaymentRequestSerializer(serializers.Serializer):
    """
    Cart payload.

    Exactly one of schematic_id / plan_id must match `purpose`.
    """

    purpose = serializers.ChoiceField(choices=PaymentTransaction.Purpose.choices)
    schematic_id = serializers.IntegerField(required=False)
    plan_id = serializers.IntegerField(required=False)

    def validate(self, attrs):
        purpose = attrs['purpose']
        if purpose == PaymentTransaction.Purpose.SCHEMATIC and not attrs.get('schematic_id'):
            raise serializers.ValidationError({'schematic_id': 'برای خرید تکی شماتیک لازم است.'})
        if purpose == PaymentTransaction.Purpose.SUBSCRIPTION and not attrs.get('plan_id'):
            raise serializers.ValidationError({'plan_id': 'برای خرید اشتراک لازم است.'})
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
