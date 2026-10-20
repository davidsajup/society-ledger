import logging
from datetime import date

from celery import shared_task

from apps.societies.models import Society

from .services import current_period, run_billing

logger = logging.getLogger(__name__)


@shared_task(name="billing.bill_society")
def bill_society(society_id: int, period_iso: str) -> dict:
    """Bill one society for one month. The unit of work, and safe to run any number of times.

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
    """Fan out one bill_society task per society for the CURRENT month.

    Beat runs this every day. That is safe because billing is idempotent: the first run of a
    month does the work and every later run is a no-op. It also means a missed 1st (scheduler
    down, deploy in progress) is caught up automatically on the next tick.
    """
    period = current_period().isoformat()
    # The one deliberate non-tenant-scoped query: a system job that must visit every tenant.
    # It only reads ids; each task then works inside a single society.
    society_ids = list(Society.objects.values_list("id", flat=True))
    for society_id in society_ids:
        bill_society.delay(society_id, period)
    return len(society_ids)
