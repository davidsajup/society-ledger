from decimal import Decimal

from rest_framework import serializers

from .models import PaymentClaim

AMOUNT = {"max_digits": 12, "decimal_places": 2, "min_value": Decimal("0.01")}


class ClaimInputSerializer(serializers.Serializer):
    """What a resident sends. The flat comes from the URL and the person from the login."""

    amount = serializers.DecimalField(**AMOUNT)
    paid_on = serializers.DateField()
    method = serializers.ChoiceField(choices=PaymentClaim.Method.choices)
    reference = serializers.CharField(max_length=60, required=False, allow_blank=True, default="")


class AcceptInputSerializer(serializers.Serializer):
    # Only when the bank shows a different figure from the one the resident gave.
    amount = serializers.DecimalField(required=False, **AMOUNT)
    confirm_duplicate = serializers.BooleanField(required=False, default=False)


class RejectInputSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=200)


class ClaimSerializer(serializers.ModelSerializer):
    flat_label = serializers.CharField(source="flat.label", read_only=True)
    claimed_by_name = serializers.SerializerMethodField()
    ledger_entry_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = PaymentClaim
        fields = [
            "id", "flat", "flat_label", "claimed_by_name", "amount", "paid_on", "method",
            "reference", "status", "resolution_note", "accepted_amount", "ledger_entry_id",
            "created_at", "resolved_at",
        ]
        read_only_fields = fields

    def get_claimed_by_name(self, obj):
        # Lists must select_related("claimed_by"). A display name, never the username.
        return obj.claimed_by.first_name or obj.claimed_by.username
