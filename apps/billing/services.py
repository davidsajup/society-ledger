from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.audit import services as audit
from apps.audit.models import AuditLog
from apps.ledger.services import record_charge
from apps.societies.models import Flat

from .models import BillingRun


def current_period(today=None, cycle_months=1) -> date:
    """First day of the billing cycle that contains `today` (project timezone, Asia/Kolkata).

    Monthly: the 1st of the month. Quarterly: the 1st of January, April, July or October. These
    are the quarter starts for both calendar years and Indian financial years.
    """
    today = today or timezone.localdate()
    first_month = today.month - (today.month - 1) % cycle_months
    return today.replace(month=first_month, day=1)


def is_cycle_start(period, cycle_months) -> bool:
    """Is `period` the first day of a cycle (any month if monthly; Jan/Apr/Jul/Oct if quarterly)?"""
    return period.day == 1 and (period.month - 1) % cycle_months == 0


def period_note(period, cycle_months) -> str:
    """The ledger note for a cycle's charge: 'Maintenance 2026-10' or 'Maintenance 2026-Q4'."""
    if cycle_months == 3:
        return f"Maintenance {period.year}-Q{(period.month - 1) // 3 + 1}"
    return f"Maintenance {period:%Y-%m}"


def run_billing(*, society, period):
    """Charge every billable flat of `society` for cycle `period`. Returns (billing_run, created).

    A cycle is a month or a quarter, per society.billing_cycle_months; `period` is its first day.

    Safe to run twice, concurrently, or after a crash:
    * everything happens in ONE transaction, so a failure rolls back the BillingRun row and
      every charge together: a cycle is either fully billed or not billed at all;
    * UNIQUE(society, period) on BillingRun means a second run finds the first and does nothing;
    * two workers racing: the second blocks on the unique index until the first commits, then
      gets an IntegrityError and returns the first worker's run instead of billing again.
    """
    if period.day != 1:
        raise ValidationError("Billing period must be the first day of a month.")
    if not is_cycle_start(period, society.billing_cycle_months):
        raise ValidationError(
            "This society is billed every "
            f"{society.billing_cycle_months} months: the period must be the first day of a cycle "
            "(January, April, July or October for quarterly billing)."
        )

    existing = BillingRun.objects.for_society(society).filter(period=period).first()
    if existing is not None:
        return existing, False

    try:
        with transaction.atomic():
            run = BillingRun.objects.create(society=society, period=period)
            charged, total = 0, Decimal("0.00")
            billable = Flat.objects.for_society(society).filter(maintenance_amount__gt=0)
            for flat in billable.order_by("id"):
                record_charge(
                    society=society,
                    flat=flat,
                    amount=flat.maintenance_amount,
                    note=period_note(period, society.billing_cycle_months),
                    billing_run=run,
                )
                charged += 1
                total += flat.maintenance_amount
            run.flats_charged = charged
            run.total_amount = total
            run.save(update_fields=["flats_charged", "total_amount"])
            # Inside the same transaction: if this write fails, the whole cycle rolls back.
            audit.record(
                society=society,
                action=AuditLog.Action.BILLING_RUN,
                object_type="billing_run",
                object_id=run.pk,
                amount=total,
                data={"period": f"{period:%Y-%m}", "flats_charged": charged},
            )
    except IntegrityError:
        # Lost the race to another worker. If their run is not there, this was some other
        # integrity problem and must not be swallowed.
        winner = BillingRun.objects.for_society(society).filter(period=period).first()
        if winner is None:
            raise
        return winner, False
    return run, True
