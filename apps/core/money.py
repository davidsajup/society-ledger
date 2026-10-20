from decimal import Decimal

from django.core.exceptions import ValidationError

CENT = Decimal("0.01")


def validate_amount(amount):
    """Money is Decimal with at most 2 decimal places and strictly positive. Never a float."""
    if not isinstance(amount, Decimal):
        raise TypeError(f"amount must be a Decimal, got {type(amount).__name__}")
    if not amount.is_finite() or amount <= 0:
        raise ValidationError("Amount must be greater than zero.")
    if amount != amount.quantize(CENT):
        raise ValidationError("Amount cannot have more than 2 decimal places.")
