from rest_framework import serializers

# Money fields are DecimalFields so they reach the browser as exact strings ("1500.00").
# A bare Decimal in a response dict would be encoded by DRF as a JSON float.


def money():
    return serializers.DecimalField(max_digits=12, decimal_places=2)


class TotalsSerializer(serializers.Serializer):
    billed = money()
    collected = money()
    outstanding = money()
    spent = money()


class FlatBalanceSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    label = serializers.CharField()
    billed = money()
    collected = money()
    outstanding = money()


class SummarySerializer(serializers.Serializer):
    totals = TotalsSerializer()
    flats = FlatBalanceSerializer(many=True)


class RecentPaymentSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    flat_id = serializers.IntegerField()
    flat_label = serializers.CharField(source="flat.label")
    amount = money()
    note = serializers.CharField()
    recorded_by = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField()
    is_reversal = serializers.SerializerMethodField()
    reversed = serializers.BooleanField()

    def get_recorded_by(self, obj):
        return obj.created_by.username if obj.created_by else "system"

    def get_is_reversal(self, obj):
        return obj.reverses_id is not None
