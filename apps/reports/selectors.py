"""Read-only views of the books for dashboards. No models, no writes.

Every figure is NET of reversals, so a reversed payment does not look like a new charge:
  billed    = charges        - reversed charges
  collected = payments       - reversed payments
  outstanding = billed - collected   (equals sum(charges) - sum(payments) in the ledger)
"""

from decimal import Decimal

from django.db.models import DecimalField, Exists, OuterRef, Q, Sum, Value
from django.db.models.functions import Coalesce

from apps.expenses.selectors import total_spent
from apps.ledger.models import LedgerEntry
from apps.societies.models import Flat

_MONEY = DecimalField(max_digits=12, decimal_places=2)
_ZERO = Value(Decimal("0.00"), output_field=_MONEY)


def _total(**conditions):
    return Coalesce(Sum("amount", filter=Q(**conditions)), _ZERO)


def society_summary(society):
    """Totals plus one row per flat (flats with no entries show zeros). Two queries."""
    grouped = (
        LedgerEntry.objects.for_society(society)
        .values("flat_id")
        .annotate(
            charged=_total(kind="charge", reverses__isnull=True),
            charge_reversed=_total(kind="payment", reverses__isnull=False),
            paid=_total(kind="payment", reverses__isnull=True),
            payment_reversed=_total(kind="charge", reverses__isnull=False),
        )
        .order_by()
    )
    by_flat = {row["flat_id"]: row for row in grouped}

    flats, billed_all, collected_all = [], Decimal("0.00"), Decimal("0.00")
    for flat in Flat.objects.for_society(society).order_by("label"):
        row = by_flat.get(flat.id)
        billed = row["charged"] - row["charge_reversed"] if row else Decimal("0.00")
        collected = row["paid"] - row["payment_reversed"] if row else Decimal("0.00")
        flats.append(
            {
                "id": flat.id,
                "label": flat.label,
                "billed": billed,
                "collected": collected,
                "outstanding": billed - collected,
            }
        )
        billed_all += billed
        collected_all += collected

    return {
        "totals": {
            "billed": billed_all,
            "collected": collected_all,
            "outstanding": billed_all - collected_all,
            "spent": total_spent(society),
        },
        "flats": flats,
    }


def recent_payments(society, limit=50):
    """Newest payment entries across the society, with what the treasurer UI needs to show a
    row and decide whether a Reverse button applies (`reversed`, `is_reversal`)."""
    reversed_already = LedgerEntry.objects.filter(reverses=OuterRef("pk"))
    return (
        LedgerEntry.objects.for_society(society)
        .filter(kind=LedgerEntry.Kind.PAYMENT)
        .select_related("flat", "created_by")
        .annotate(reversed=Exists(reversed_already))
        .order_by("-created_at", "-id")[:limit]
    )
