from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.audit import services as audit
from apps.audit.models import AuditLog
from apps.ledger.services import record_charge
from apps.societies.models import Flat, Society

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


class BillingAlreadyStarted(Exception):
    """A billing run exists, so the cycle and start date are locked."""


def validate_billing_schedule(*, cycle_months, start):
    """Raise a field-keyed ValidationError unless (cycle, start) is a schedule we can run.

    `start` is the first cycle to be charged: the first day of a cycle, not in the past. The
    same rule applies when the super admin onboards a society and when the president changes
    the schedule.
    """
    if cycle_months not in (1, 3):
        raise ValidationError({"billing_cycle_months": "Choose every month or every 3 months."})
    if start is None:
        return
    if not is_cycle_start(start, cycle_months):
        raise ValidationError(
            {
                "billing_start": "Billing must start on the first day of a cycle "
                "(the 1st of January, April, July or October for quarterly billing)."
            }
        )
    if start < timezone.localdate():
        raise ValidationError({"billing_start": "The billing start date cannot be in the past."})


def billing_has_started(society) -> bool:
    return BillingRun.objects.for_society(society).exists()


@transaction.atomic
def change_billing_settings(*, society, actor, cycle_months, start, amounts_reviewed=False):
    """Change how often `society` is billed and when billing starts. Returns (society, changed).

    Allowed only until the first billing run exists. After that charges are in the append-only
    ledger and every amount means "per cycle", so the schedule is fixed.

    The society row is locked first, and run_billing takes the same lock. Without it the daily
    job could bill under the old schedule while this saves the new one (check-then-act): both
    would succeed and a run would exist that the new schedule forbids.

    A different cycle changes what every flat's amount MEANS (4500 per quarter is not 4500 per
    month), so the caller must say the amounts have been reviewed when any flat has one.
    """
    society = Society.objects.select_for_update().get(pk=society.pk)
    if billing_has_started(society):
        raise BillingAlreadyStarted(
            "Billing has already started, so the billing cycle and start date can no longer "
            "be changed."
        )
    if start is None:
        raise ValidationError({"billing_start": "Choose the date billing starts."})
    validate_billing_schedule(cycle_months=cycle_months, start=start)

    if (cycle_months, start) == (society.billing_cycle_months, society.billing_start):
        return society, False

    cycle_changed = cycle_months != society.billing_cycle_months
    has_amounts = Flat.objects.for_society(society).filter(maintenance_amount__gt=0).exists()
    if cycle_changed and has_amounts and not amounts_reviewed:
        raise ValidationError(
            {
                "amounts_reviewed": "Each flat's amount is for one billing cycle. Check every "
                "flat's amount for the new cycle, then confirm that you have."
            }
        )

    before = {
        "from_cycle_months": society.billing_cycle_months,
        "from_start": society.billing_start.isoformat() if society.billing_start else None,
    }
    society.billing_cycle_months = cycle_months
    society.billing_start = start
    society.save(update_fields=["billing_cycle_months", "billing_start"])
    audit.record(
        society=society,
        actor=actor,
        action=AuditLog.Action.BILLING_SETTINGS_CHANGED,
        object_type="society",
        object_id=society.pk,
        data={
            **before,
            "to_cycle_months": cycle_months,
            "to_start": start.isoformat(),
            "amounts_reviewed": bool(amounts_reviewed),
        },
    )
    return society, True


def _check_period(society, period):
    """Refuse a period this society's schedule does not allow (nothing is written)."""
    if period.day != 1:
        raise ValidationError("Billing period must be the first day of a month.")
    if not is_cycle_start(period, society.billing_cycle_months):
        raise ValidationError(
            "This society is billed every "
            f"{society.billing_cycle_months} months: the period must be the first day of a cycle "
            "(January, April, July or October for quarterly billing)."
        )
    if society.billing_start is not None and period < society.billing_start:
        # Every way into billing (the daily job, the command, a future screen) ends up here, so
        # one check protects them all. The job also filters on billing_start, but this is the
        # door that cannot be forgotten: a charge in the append-only ledger cannot be deleted.
        raise ValidationError(
            f"Billing for this society starts on {society.billing_start:%d %B %Y}. "
            f"It cannot be billed for {period:%B %Y}."
        )


def run_billing(*, society, period):
    """Charge every billable flat of `society` for cycle `period`. Returns (billing_run, created).

    A cycle is a month or a quarter, per society.billing_cycle_months; `period` is its first day.
    A society with a billing_start date cannot be billed for any cycle before it.

    Safe to run twice, concurrently, or after a crash:
    * everything happens in ONE transaction, so a failure rolls back the BillingRun row and
      every charge together: a cycle is either fully billed or not billed at all;
    * UNIQUE(society, period) on BillingRun means a second run finds the first and does nothing;
    * two workers racing: the second blocks on the unique index until the first commits, then
      gets an IntegrityError and returns the first worker's run instead of billing again.
    """
    _check_period(society, period)  # a quick refusal before any database work

    existing = BillingRun.objects.for_society(society).filter(period=period).first()
    if existing is not None:
        return existing, False

    try:
        with transaction.atomic():
            # Same lock as change_billing_settings. Re-read the society now that we hold it: the
            # object we were given may predate a schedule change that committed while we waited.
            society = Society.objects.select_for_update().get(pk=society.pk)
            _check_period(society, period)
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
