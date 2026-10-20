from decimal import Decimal

from rest_framework import serializers

from .models import LedgerEntry


class PaymentInputSerializer(serializers.Serializer):
    # DecimalField parses straight into Decimal (a float never reaches the ledger) and refuses
    # more than 2 decimal places. Output is a string (COERCE_DECIMAL_TO_STRING).
    amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0.01")
    )
    note = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")


class ReversalInputSerializer(serializers.Serializer):
    note = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")


class LedgerEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = LedgerEntry
        fields = ["id", "flat", "kind", "amount", "note", "reverses", "created_at"]
        read_only_fields = fields


class FlatSummarySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    label = serializers.CharField()


class FlatLedgerSerializer(serializers.Serializer):
    """Response shape for GET /ledger/.

    `outstanding` MUST go through a DecimalField: a bare Decimal in a response dict is encoded
    by DRF as a JSON float (70.0), while a DecimalField renders the exact string "70.00".
    """

    flat = FlatSummarySerializer()
    outstanding = serializers.DecimalField(max_digits=12, decimal_places=2)
    entries = LedgerEntrySerializer(many=True)
