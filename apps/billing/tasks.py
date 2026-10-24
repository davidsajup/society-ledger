import logging
from datetime import date

from celery import shared_task
from django.utils import timezone

from apps.societies.models import Society

from .services import current_period, run_billing

logger = logging.getLogger(__name__)


@shared_task(name="billing.bill_society")
def bill_society(society_id: int, period_iso: str) -> dict:
    """Bill one society for one cycle. The unit of work, and safe to run any number of times.

    Arguments are plain JSON types (an int and an ISO string) so the message is small and
    survives the broker; the task loads fresh rows itself.
    """
    society = Society.objects.filter(pk=society_id).first()
    if society is None:
        logger.warning("bill_society: society %s no longer exists", society_id)
        return {"society_id": society_id, "status": "missing"}

    run, created = run_billing(society=society, period=date.fromisoformat(period_iso))
    logger.info(
        "billing society=%s period=%s %s (flats=%s total=%s)",
        society_id, period_iso, "created" if created else "already done",
        run.flats_charged, run.total_amount,
    )
    return {
        "society_id": society_id,
        "period": period_iso,
        "status": "created" if created else "already_done",
        "flats_charged": run.flats_charged,
        "total_amount": str(run.total_amount),  # Decimal is not JSON; a string stays exact
    }


@shared_task(name="billing.bill_all_societies")
def bill_all_societies() -> int:
    """Fan out one bill_society task per society for its CURRENT billing cycle.

    Beat runs this every day. That is safe because billing is idempotent: the first run of a
    cycle does the work and every later run is a no-op. It also means a missed first day
    (scheduler down, deploy in progress) is caught up automatically on the next tick.

    The cycle is per society (a month or a quarter), and a society is skipped until its
    billing_start date, so flats and amounts can be set up mid-cycle without an early charge.
    """
    today = timezone.localdate()
    queued = 0
    # The one deliberate non-tenant-scoped query: a system job that must visit every tenant.
    # It only reads a few plain columns; each task then works inside a single society.
    for society_id, cycle, start in Society.objects.values_list(
        "id", "billing_cycle_months", "billing_start"
    ):
        if start is not None and today < start:
            continue
        bill_society.delay(society_id, current_period(today, cycle).isoformat())
        queued += 1
    return queued
