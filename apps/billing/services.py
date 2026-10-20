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


def current_period(today=None) -> date:
    """First day of the current month, in the project's timezone (Asia/Kolkata)."""
    today = today or timezone.localdate()
    return today.replace(day=1)


def run_billing(*, society, period):
    """Charge every billable flat of `society` for month `period`. Returns (billing_run, created).

    Safe to run twice, concurrently, or after a crash:
    * everything happens in ONE transaction, so a failure rolls back the BillingRun row and
      every charge together: a month is either fully billed or not billed at all;
    * UNIQUE(society, period) on BillingRun means a second run finds the first and does nothing;
    * two workers racing: the second blocks on the unique index until the first commits, then
      gets an IntegrityError and returns the first worker's run instead of billing again.
    """
    if period.day != 1:
        raise ValidationError("Billing period must be the first day of a month.")

    existing = BillingRun.objects.for_society(society).filter(period=period).first()
    if existing is not None:
        return existing, False

    try:
        with transaction.atomic():
            run = BillingRun.objects.create(society=society, period=period)
            charged, total = 0, Decimal("0.00")
            billable = Flat.objects.for_society(society).filter(monthly_maintenance__gt=0)
            for flat in billable.order_by("id"):
                record_charge(
                    society=society,
                    flat=flat,
                    amount=flat.monthly_maintenance,
                    note=f"Maintenance {period:%Y-%m}",
                    billing_run=run,
                )
                charged += 1
                total += flat.monthly_maintenance
            run.flats_charged = charged
            run.total_amount = total
            run.save(update_fields=["flats_charged", "total_amount"])
            # Inside the same transaction: if this write fails, the whole month rolls back.
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
