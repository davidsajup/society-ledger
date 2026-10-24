from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.billing import services
from apps.billing.models import BillingRun
from apps.billing.services import current_period, run_billing
from apps.ledger.models import LedgerEntry
from apps.ledger.selectors import outstanding_for_flat
from apps.ledger.tests.helpers import run_in_parallel
from apps.societies.models import Flat, Society

D = Decimal
NOV = date(2026, 11, 1)
DEC = date(2026, 12, 1)


def make_society(slug="green-park", amounts=("1500.00", "2000.50", "0.00")):
    society = Society.objects.create(name=slug, slug=slug)
    flats = [
        Flat.objects.create(society=society, label=f"A-{i}", maintenance_amount=D(a))
        for i, a in enumerate(amounts, start=101)
    ]
    return society, flats


def charges(society):
    return LedgerEntry.objects.for_society(society).filter(kind="charge")


# --- What a billing run does ----------------------------------------------------------------


@pytest.mark.django_db
def test_billing_charges_each_billable_flat_once_and_skips_zero_flats():
    society, (a, b, free) = make_society()

    run, created = run_billing(society=society, period=NOV)

    assert created is True
    assert (run.flats_charged, run.total_amount) == (2, D("3500.50"))
    assert outstanding_for_flat(a) == D("1500.00")
    assert outstanding_for_flat(b) == D("2000.50")
    assert outstanding_for_flat(free) == D("0.00")
    entry = charges(society).get(flat=a)
    assert (entry.billing_run, entry.created_by, entry.note) == (run, None, "Maintenance 2026-11")


@pytest.mark.django_db
def test_billing_total_is_exact_with_cents():
    society, _ = make_society(amounts=("0.10", "0.20"))

    run, _ = run_billing(society=society, period=NOV)

    assert run.total_amount == D("0.30")


# --- Idempotency: the guarantee this milestone exists to prove ------------------------------


@pytest.mark.django_db
def test_running_the_job_twice_creates_no_second_charges():
    """Proves: a re-run (restart, retry, duplicate beat tick) never double-bills a flat."""
    society, _ = make_society()
    first, first_created = run_billing(society=society, period=NOV)
    ledger_after_first = list(charges(society).values_list("id", flat=True))

    second, second_created = run_billing(society=society, period=NOV)

    assert (first_created, second_created) == (True, False)
    assert first.pk == second.pk
    assert list(charges(society).values_list("id", flat=True)) == ledger_after_first
    assert BillingRun.objects.count() == 1


@pytest.mark.django_db
def test_a_new_month_is_billed_separately():
    society, (a, *_) = make_society()
    run_billing(society=society, period=NOV)

    run_billing(society=society, period=DEC)

    assert BillingRun.objects.count() == 2
    assert outstanding_for_flat(a) == D("3000.00")


@pytest.mark.django_db
def test_a_flat_added_after_the_run_is_not_billed_until_next_month():
    society, _ = make_society()
    run_billing(society=society, period=NOV)
    latecomer = Flat.objects.create(society=society, label="Z-9", maintenance_amount=D("999.00"))

    run_billing(society=society, period=NOV)  # re-run of an already-billed month

    assert outstanding_for_flat(latecomer) == D("0.00")


@pytest.mark.django_db(transaction=True)
def test_ten_simultaneous_runs_bill_each_flat_exactly_once(monkeypatch):
    """Proves: two workers (or a double-fired beat) racing on the same month cannot double-bill.

    The sleep widens the window between starting the run and finishing it, so every thread is
    genuinely inside the race.
    """
    import time

    real = services.record_charge

    def slow(**kwargs):
        entry = real(**kwargs)
        time.sleep(0.02)
        return entry

    monkeypatch.setattr(services, "record_charge", slow)
    society, flats = make_society()

    results = run_in_parallel(10, lambda _: run_billing(society=society, period=NOV))

    assert [created for _, created in results].count(True) == 1
    assert len({run.pk for run, _ in results}) == 1
    assert BillingRun.objects.count() == 1
    assert charges(society).count() == 2  # two billable flats, one charge each
    assert outstanding_for_flat(flats[0]) == D("1500.00")


# --- Atomicity ------------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_a_crash_halfway_leaves_nothing_behind_and_a_rerun_succeeds(monkeypatch):
    """Proves: the month is billed completely or not at all, never half-billed."""
    society, flats = make_society()
    real = services.record_charge
    calls = {"n": 0}

    def explode_on_second_flat(**kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("worker died")
        return real(**kwargs)

    monkeypatch.setattr(services, "record_charge", explode_on_second_flat)

    with pytest.raises(RuntimeError):
        run_billing(society=society, period=NOV)

    assert BillingRun.objects.count() == 0  # the run row rolled back with the charges
    assert charges(society).count() == 0  # the first flat's charge rolled back too

    monkeypatch.setattr(services, "record_charge", real)
    run, created = run_billing(society=society, period=NOV)
    assert created is True
    assert outstanding_for_flat(flats[0]) == D("1500.00")  # billed once, after the retry


# --- Tenant isolation -----------------------------------------------------------------------


@pytest.mark.django_db
def test_billing_one_society_never_touches_another():
    green, (g1, *_) = make_society("green-park")
    lake, (l1, *_) = make_society("lake-view", amounts=("700.00",))

    run_billing(society=green, period=NOV)

    assert outstanding_for_flat(l1) == D("0.00")
    assert not BillingRun.objects.filter(society=lake).exists()
    assert not charges(lake).exists()
    # ...and the other society can still be billed for the same month afterwards.
    _, created = run_billing(society=lake, period=NOV)
    assert created is True
    assert outstanding_for_flat(l1) == D("700.00")


# --- Validation and database constraints ----------------------------------------------------


@pytest.mark.django_db
def test_period_must_be_the_first_of_a_month():
    society, _ = make_society()

    with pytest.raises(ValidationError):
        run_billing(society=society, period=date(2026, 11, 15))
    assert not BillingRun.objects.exists()


@pytest.mark.django_db
def test_database_rejects_a_second_run_for_the_same_society_and_period():
    society, _ = make_society()
    BillingRun.objects.create(society=society, period=NOV)

    with pytest.raises(IntegrityError), transaction.atomic():
        BillingRun.objects.create(society=society, period=NOV)


@pytest.mark.django_db
def test_database_rejects_a_mid_month_period():
    society, _ = make_society()

    with pytest.raises(IntegrityError), transaction.atomic():
        BillingRun.objects.create(society=society, period=date(2026, 11, 2))


@pytest.mark.django_db
def test_database_rejects_two_charges_for_one_flat_in_one_run():
    """The second, independent guard: even bypassing run_billing, the ledger refuses."""
    society, (flat, *_) = make_society()
    run = BillingRun.objects.create(society=society, period=NOV)
    LedgerEntry.objects.create(
        society=society, flat=flat, kind="charge", amount=D("5.00"), billing_run=run
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        LedgerEntry.objects.create(
            society=society, flat=flat, kind="charge", amount=D("5.00"), billing_run=run
        )


@pytest.mark.django_db
def test_database_rejects_negative_maintenance():
    society, _ = make_society()

    with pytest.raises(IntegrityError), transaction.atomic():
        Flat.objects.create(society=society, label="N-1", maintenance_amount=D("-1.00"))


def test_current_period_is_the_first_of_the_month():
    assert current_period(date(2026, 11, 20)) == NOV
    assert current_period(date(2026, 12, 1)) == DEC
