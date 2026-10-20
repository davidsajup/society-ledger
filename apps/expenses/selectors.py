from decimal import Decimal

from django.db.models import Case, DecimalField, F, Sum, Value, When
from django.db.models.functions import Coalesce

from .models import Expense

_MONEY = DecimalField(max_digits=12, decimal_places=2)


def total_spent(society) -> Decimal:
    """Spending minus reversed spending, computed in the database. Scoped to one society."""
    signed = Case(
        When(reverses__isnull=True, then=F("amount")),
        default=-F("amount"),
        output_field=_MONEY,
    )
    return Expense.objects.for_society(society).aggregate(
        total=Coalesce(Sum(signed), Value(Decimal("0.00"), output_field=_MONEY))
    )["total"]
