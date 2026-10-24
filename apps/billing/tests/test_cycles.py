"""Quarterly billing: one charge per flat every 3 months, safe to run every day, flexible to pay.

What these tests prove
* The cycle maths: any date in a quarter belongs to that quarter's first day (Jan/Apr/Jul/Oct).
* A quarterly society cannot be billed for a month that is not a quarter start (no stray charge).
* The daily job is per society: a monthly and a quarterly society bill correctly in the same run.
* The daily job is idempotent across a whole quarter, and never bills before a society's
  billing_start date (setting up flats mid-quarter cannot trigger a surprise charge).
* Flexible payments: a quarterly charge can be paid in installments, but never overpaid.
* The dues grid works on quarterly periods.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.billing.models import BillingRun
from apps.billing.services import current_period, is_cycle_start, period_note, run_billing
from apps.billing.tasks import bill_all_societies
from apps.ledger.models import LedgerEntry
from apps.ledger.selectors import outstanding_for_flat
from apps.ledger.services import PaymentExceedsOutstanding, record_payment
from apps.reports.dues import dues_grid
from apps.societies.models import Flat, Society
from apps.societies.services import add_member

pytestmark = pytest.mark.django_db
D = Decimal


@pytest.fixture
def quarterly():
    society = Society.objects.create(
        name="Green Meadows", slug="green-meadows", billing_cycle_months=3
    )
    flat = Flat.objects.create(society=society, label="A-1", maintenance_amount=D("4500.00"))
    return society, flat


def pretend_today(monkeypatch, day):
    monkeypatch.setattr("apps.billing.tasks.timezone.localdate", lambda: day)


# --- the cycle maths ----------------------------------


@pytest.mark.parametrize(
    "today, expected",
    [
        (date(2026, 10, 1), date(2026, 10, 1)),
        (date(2026, 11, 15), date(2026, 10, 1)),
        (date(2026, 12, 31), date(2026, 10, 1)),
        (date(2027, 1, 1), date(2027, 1, 1)),
        (date(2027, 2, 28), date(2027, 1, 1)),
        (date(2027, 6, 30), date(2027, 4, 1)),
        (date(2027, 9, 9), date(2027, 7, 1)),
    ],
)
def test_a_quarterly_period_is_the_first_day_of_the_quarter(today, expected):
    assert current_period(today, cycle_months=3) == expected


def test_a_monthly_period_is_still_the_first_of_the_month():
    assert current_period(date(2026, 11, 15)) == date(2026, 11, 1)
    assert current_period(date(2026, 11, 15), cycle_months=1) == date(2026, 11, 1)


def test_which_dates_start_a_cycle():
    assert is_cycle_start(date(2026, 11, 1), 1)
    assert is_cycle_start(date(2026, 10, 1), 3)
    assert not is_cycle_start(date(2026, 11, 1), 3)
    assert not is_cycle_start(date(2026, 10, 2), 3)


def test_the_ledger_note_names_the_quarter():
    assert period_note(date(2026, 10, 1), 3) == "Maintenance 2026-Q4"
    assert period_note(date(2027, 1, 1), 3) == "Maintenance 2027-Q1"
    assert period_note(date(2026, 11, 1), 1) == "Maintenance 2026-11"


# --- billing a quarterly society ----------------------------------


def test_a_quarter_is_billed_once_with_one_charge_per_flat(quarterly):
    society, flat = quarterly

    run, created = run_billing(society=society, period=date(2026, 10, 1))
    again, created_again = run_billing(society=society, period=date(2026, 10, 1))

    assert (created, created_again) == (True, False)
    assert again.pk == run.pk
    entry = LedgerEntry.objects.get(flat=flat)
    assert entry.amount == D("4500.00")
    assert entry.note == "Maintenance 2026-Q4"


@pytest.mark.parametrize("period", [date(2026, 11, 1), date(2026, 12, 1), date(2026, 10, 2)])
def test_a_quarterly_society_refuses_a_non_quarter_start_period(quarterly, period):
    society, flat = quarterly

    with pytest.raises(ValidationError):
        run_billing(society=society, period=period)

    assert BillingRun.objects.count() == 0
    assert LedgerEntry.objects.count() == 0


# --- the daily job ----------------------------------


def test_the_daily_job_bills_each_society_for_its_own_cycle(monkeypatch, quarterly):
    q_society, q_flat = quarterly
    monthly = Society.objects.create(name="Lake View", slug="lake-view")
    m_flat = Flat.objects.create(society=monthly, label="B-1", maintenance_amount=D("700.00"))
    pretend_today(monkeypatch, date(2026, 11, 15))

    assert bill_all_societies.delay().get() == 2

    periods = {r.society_id: r.period for r in BillingRun.objects.all()}
    assert periods == {q_society.id: date(2026, 10, 1), monthly.id: date(2026, 11, 1)}
    assert outstanding_for_flat(q_flat) == D("4500.00")
    assert outstanding_for_flat(m_flat) == D("700.00")


def test_the_daily_job_charges_a_quarterly_flat_once_however_many_days_it_runs(
    monkeypatch, quarterly
):
    _, flat = quarterly

    for day in (date(2026, 10, 1), date(2026, 10, 2), date(2026, 11, 20), date(2026, 12, 31)):
        pretend_today(monkeypatch, day)
        bill_all_societies.delay().get()

    assert BillingRun.objects.count() == 1
    assert LedgerEntry.objects.filter(flat=flat).count() == 1

    pretend_today(monkeypatch, date(2027, 1, 1))  # the next quarter begins
    bill_all_societies.delay().get()

    assert BillingRun.objects.count() == 2
    assert outstanding_for_flat(flat) == D("9000.00")


def test_a_society_is_not_billed_before_its_billing_start(monkeypatch, quarterly):
    """Flats and amounts set up in December must not be charged for October-December."""
    society, flat = quarterly
    society.billing_start = date(2027, 1, 1)
    society.save()

    pretend_today(monkeypatch, date(2026, 12, 15))
    assert bill_all_societies.delay().get() == 0
    assert BillingRun.objects.count() == 0
    assert LedgerEntry.objects.count() == 0

    pretend_today(monkeypatch, date(2027, 1, 2))  # first tick after the start date
    assert bill_all_societies.delay().get() == 1
    assert BillingRun.objects.get().period == date(2027, 1, 1)
    assert outstanding_for_flat(flat) == D("4500.00")


# --- flexible payments ----------------------------------


def test_a_quarterly_charge_is_payable_in_installments_but_never_overpaid(quarterly):
    society, flat = quarterly
    treasurer = add_member_user(society, "tara", "treasurer")
    run_billing(society=society, period=date(2026, 10, 1))

    for month in ("Oct", "Nov", "Dec"):
        record_payment(
            society=society, flat=flat, amount=D("1500.00"), actor=treasurer,
            idempotency_key=f"installment-{month}",
        )

    assert outstanding_for_flat(flat) == D("0.00")
    with pytest.raises(PaymentExceedsOutstanding):  # paying ahead is not supported (yet)
        record_payment(society=society, flat=flat, amount=D("1.00"), actor=treasurer)


def test_one_payment_larger_than_the_quarter_is_still_refused(quarterly):
    society, flat = quarterly
    treasurer = add_member_user(society, "tara", "treasurer")
    run_billing(society=society, period=date(2026, 10, 1))

    with pytest.raises(PaymentExceedsOutstanding):
        record_payment(society=society, flat=flat, amount=D("4500.01"), actor=treasurer)


def add_member_user(society, username, role):
    from django.contrib.auth import get_user_model

    user = get_user_model().objects.create_user(username=username, password="x")
    add_member(society=society, user=user, role=role)
    return user


# --- reports ----------------------------------


def test_the_dues_grid_has_a_column_per_quarter_and_says_so(quarterly):
    society, flat = quarterly
    treasurer = add_member_user(society, "tara", "treasurer")
    run_billing(society=society, period=date(2026, 10, 1))
    run_billing(society=society, period=date(2027, 1, 1))
    record_payment(society=society, flat=flat, amount=D("4500.00"), actor=treasurer)

    grid = dues_grid(society)

    assert grid["cycle_months"] == 3
    assert grid["periods"] == [date(2026, 10, 1), date(2027, 1, 1)]
    cells = grid["flats"][0]["cells"]
    assert [c["status"] for c in cells] == ["paid", "unpaid"]  # oldest dues are paid first
    assert grid["summary"]["oldest_unpaid"] == date(2027, 1, 1)
