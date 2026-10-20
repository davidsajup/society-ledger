from decimal import Decimal

from rest_framework import serializers

from .models import Expense


class ExpenseInputSerializer(serializers.Serializer):
    category = serializers.ChoiceField(choices=Expense.Category.choices)
    description = serializers.CharField(max_length=200)
    amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0.01")
    )
    paid_on = serializers.DateField()


class ExpenseSerializer(serializers.ModelSerializer):
    created_by = serializers.CharField(source="created_by.username", read_only=True)

    class Meta:
        model = Expense
        fields = [
            "id", "category", "description", "amount", "paid_on", "created_by", "reverses",
            "created_at",
        ]
        read_only_fields = fields


class ExpenseListSerializer(serializers.Serializer):
    """Response shape for GET /expenses/. `total_spent` goes through a DecimalField so it is the
    exact string "250.50" on the wire; a bare Decimal in a response dict becomes a JSON float."""

    total_spent = serializers.DecimalField(max_digits=12, decimal_places=2)
    expenses = ExpenseSerializer(many=True)
