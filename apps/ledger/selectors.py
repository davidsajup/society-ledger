from decimal import Decimal

from django.db.models import Case, DecimalField, F, Sum, Value, When
from django.db.models.functions import Coalesce

from .models import LedgerEntry

_MONEY = DecimalField(max_digits=12, decimal_places=2)
_ZERO = Value(Decimal("0.00"), output_field=_MONEY)


def outstanding_for_flat(flat) -> Decimal:
    """What the flat currently owes: sum(charges) - sum(payments), computed in the database.

    Derived from the ledger every time (no cached column to drift). Positive means the flat
    owes money. Scoped by society AND flat.
    """
    signed = Case(
        When(kind=LedgerEntry.Kind.CHARGE, then=F("amount")),
        When(kind=LedgerEntry.Kind.PAYMENT, then=-F("amount")),
        output_field=_MONEY,
    )
    total = (
        LedgerEntry.objects.for_society(flat.society_id)
        .filter(flat=flat)
        .aggregate(total=Coalesce(Sum(signed), _ZERO))["total"]
    )
    return total
