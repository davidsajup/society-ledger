"""Dues by month: for each flat, which billed months are paid, partly paid or unpaid.

The ledger only knows "charges" and "payments"; it does not say which month a payment is for.
This report DERIVES that by the usual rule of a society's books: money received is applied to
the OLDEST dues first. It is a view, never stored, so it can never disagree with the ledger:
for every flat, the unpaid amounts across all months add up exactly to its ledger balance.

How entries are counted (all reversals are netted, never double counted):
  charge, not a reversal      -> billed in its month (the billing run's month, else its own)
  payment that reverses charge -> cancels that charge in the ORIGINAL charge's month
  payment, not a reversal      -> money collected
  charge that reverses payment -> money collected goes back down
"""

from collections import defaultdict
from datetime import date
from decimal import Decimal

from django.utils import timezone

from apps.ledger.models import LedgerEntry
from apps.societies.models import Flat

ZERO = Decimal("0.00")


def _month_of(run_period, created_at) -> date:
    """The billing month of a charge: its billing run's period, else the month it was created."""
    return run_period or timezone.localtime(created_at).date().replace(day=1)


def _status(billed: Decimal, due: Decimal) -> str:
    if billed <= 0:
        return "none"
    if due == 0:
        return "paid"
    return "unpaid" if due == billed else "partial"


def dues_grid(society, max_periods: int = 12):
    """Return {"periods": [...], "flats": [...], "summary": {...}} for one society (2 queries)."""
    entries = (
        LedgerEntry.objects.for_society(society)
        .order_by("created_at", "id")
        .values(
            "flat_id",
            "kind",
            "amount",
            "reverses_id",
            "created_at",
            "billing_run__period",
            "reverses__billing_run__period",
            "reverses__created_at",
        )
    )

    billed = defaultdict(lambda: defaultdict(lambda: ZERO))  # flat -> month -> amount
    collected = defaultdict(lambda: ZERO)  # flat -> amount
    for e in entries:
        flat_id, amount, is_reversal = e["flat_id"], e["amount"], e["reverses_id"] is not None
        if e["kind"] == "charge" and not is_reversal:
            billed[flat_id][_month_of(e["billing_run__period"], e["created_at"])] += amount
        elif e["kind"] == "payment" and is_reversal:
            original = _month_of(e["reverses__billing_run__period"], e["reverses__created_at"])
            billed[flat_id][original] -= amount
        elif e["kind"] == "payment":
            collected[flat_id] += amount
        else:
            collected[flat_id] -= amount

    all_periods = sorted({p for months in billed.values() for p, amt in months.items() if amt != 0})
    shown = all_periods[-max_periods:]

    rows, flats_with_dues, oldest_unpaid = [], 0, None
    for flat in Flat.objects.for_society(society).order_by("label"):
        remaining = collected[flat.id]
        outstanding, cells = ZERO, {}
        for period in all_periods:  # oldest first: this is where "oldest dues first" happens
            amount = billed[flat.id][period]
            paid = min(max(remaining, ZERO), amount) if amount > 0 else ZERO
            remaining -= paid
            due = amount - paid
            outstanding += due
            cells[period] = {
                "period": period,
                "billed": max(amount, ZERO),
                "paid": paid,
                "due": max(due, ZERO),
                "status": _status(amount, due),
            }
            if due > 0 and (oldest_unpaid is None or period < oldest_unpaid):
                oldest_unpaid = period
        if outstanding > 0:
            flats_with_dues += 1
        rows.append(
            {
                "id": flat.id,
                "label": flat.label,
                "outstanding": outstanding,
                "cells": [cells[p] for p in shown],
            }
        )

    return {
        "periods": shown,
        "flats": rows,
        "summary": {
            "flats": len(rows),
            "flats_with_dues": flats_with_dues,
            "oldest_unpaid": oldest_unpaid,
        },
    }
