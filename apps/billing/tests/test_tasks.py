from datetime import date
from decimal import Decimal
from io import StringIO

import pytest
from celery.schedules import crontab
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.billing.models import BillingRun
from apps.billing.tasks import bill_all_societies, bill_society
from apps.ledger.models import LedgerEntry
from apps.ledger.selectors import outstanding_for_flat
from apps.societies.models import Flat, Society

D = Decimal
NOV = date(2026, 11, 1)


@pytest.fixture
def two_societies():
    green = Society.objects.create(name="Green Park", slug="green-park")
    lake = Society.objects.create(name="Lake View", slug="lake-view")
    g = Flat.objects.create(society=green, label="A-1", maintenance_amount=D("1500.00"))
    l = Flat.objects.create(society=lake, label="B-1", maintenance_amount=D("700.00"))  # noqa: E741
    return green, lake, g, l


@pytest.mark.django_db
def test_bill_society_task_returns_json_safe_summary_and_is_idempotent(two_societies):
    green, *_ = two_societies

    first = bill_society.delay(green.id, "2026-11-01").get()
    second = bill_society.delay(green.id, "2026-11-01").get()

    assert first == {
        "society_id": green.id,
        "period": "2026-11-01",
        "status": "created",
        "flats_charged": 1,
        "total_amount": "1500.00",  # a string: Decimal cannot go through the broker as JSON
    }
    assert second["status"] == "already_done"
    assert LedgerEntry.objects.filter(kind="charge").count() == 1


@pytest.mark.django_db
def test_bill_society_for_a_deleted_society_is_a_harmless_noop():
    assert bill_society.delay(999_999, "2026-11-01").get()["status"] == "missing"


@pytest.mark.django_db
def test_daily_fan_out_bills_every_society_once_even_when_it_fires_every_day(
    two_societies, monkeypatch
):
    green, lake, g, l = two_societies  # noqa: E741
    monkeypatch.setattr("apps.billing.tasks.current_period", lambda today=None, cycle_months=1: NOV)

    assert bill_all_societies.delay().get() == 2
    bill_all_societies.delay().get()  # the next day's tick
    bill_all_societies.delay().get()  # and the day after

    assert BillingRun.objects.count() == 2
    assert outstanding_for_flat(g) == D("1500.00")
    assert outstanding_for_flat(l) == D("700.00")


@pytest.mark.django_db
def test_a_missed_first_of_month_is_caught_up_by_a_later_tick(two_societies, monkeypatch):
    """Scheduler was down on the 1st. The tick on the 3rd bills the month, exactly once."""
    _, _, g, _ = two_societies
    monkeypatch.setattr("apps.billing.tasks.current_period", lambda today=None, cycle_months=1: NOV)

    bill_all_societies.delay().get()

    assert outstanding_for_flat(g) == D("1500.00")


def test_beat_schedule_points_at_a_registered_task_and_runs_daily():
    entry = settings.CELERY_BEAT_SCHEDULE["bill-all-societies-daily"]

    assert entry["task"] == bill_all_societies.name == "billing.bill_all_societies"
    assert isinstance(entry["schedule"], crontab)
    assert settings.CELERY_TASK_ACKS_LATE is True  # redelivery after a crash is safe: idempotent


@pytest.mark.django_db
def test_management_command_bills_and_then_reports_already_billed(two_societies):
    out = StringIO()

    call_command("run_billing", "--period", "2026-11", stdout=out)
    call_command("run_billing", "--period", "2026-11", stdout=out)

    lines = out.getvalue().splitlines()
    assert [("billed" in line and "already" not in line) for line in lines] == [
        True, True, False, False,
    ]
    assert BillingRun.objects.count() == 2


@pytest.mark.django_db
def test_management_command_rejects_a_malformed_period():
    with pytest.raises(CommandError):
        call_command("run_billing", "--period", "november")
