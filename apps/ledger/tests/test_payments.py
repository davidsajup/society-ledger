from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.ledger.models import LedgerEntry
from apps.ledger.selectors import outstanding_for_flat
from apps.ledger.services import (
    IdempotencyKeyReused,
    PaymentExceedsOutstanding,
    record_charge,
    record_payment,
)
from apps.ledger.tests.helpers import build_world, run_in_parallel
from apps.societies.models import Flat, Society

D = Decimal


# --- Sequential behaviour -------------------------------------------------------------------


@pytest.mark.django_db
def test_payment_reduces_what_is_owed():
    society, flat, treasurer = build_world("100.00")

    entry, created = record_payment(society=society, flat=flat, amount=D("30.00"), actor=treasurer)

    assert created is True
    assert (entry.kind, entry.created_by) == ("payment", treasurer)
    assert outstanding_for_flat(flat) == D("70.00")


@pytest.mark.django_db
def test_overpayment_is_rejected_and_writes_nothing():
    society, flat, treasurer = build_world("100.00")

    with pytest.raises(PaymentExceedsOutstanding) as exc:
        record_payment(society=society, flat=flat, amount=D("100.01"), actor=treasurer)

    assert exc.value.outstanding == D("100.00")
    assert LedgerEntry.objects.filter(kind="payment").count() == 0


@pytest.mark.django_db
def test_paying_exactly_what_is_owed_is_allowed_then_nothing_more():
    society, flat, treasurer = build_world("100.00")
    record_payment(society=society, flat=flat, amount=D("100.00"), actor=treasurer)

    assert outstanding_for_flat(flat) == D("0.00")
    with pytest.raises(PaymentExceedsOutstanding):
        record_payment(society=society, flat=flat, amount=D("0.01"), actor=treasurer)


@pytest.mark.django_db
def test_flat_with_no_charges_cannot_receive_a_payment():
    society, flat, treasurer = build_world(owed=None)

    with pytest.raises(PaymentExceedsOutstanding):
        record_payment(society=society, flat=flat, amount=D("1.00"), actor=treasurer)


@pytest.mark.django_db
def test_float_and_bad_amounts_are_rejected():
    society, flat, treasurer = build_world()

    with pytest.raises(TypeError):
        record_payment(society=society, flat=flat, amount=30.0, actor=treasurer)
    with pytest.raises(ValidationError):
        record_payment(society=society, flat=flat, amount=D("0.001"), actor=treasurer)


@pytest.mark.django_db
def test_payment_for_a_flat_of_another_society_is_rejected():
    society, _, treasurer = build_world()
    other = Society.objects.create(name="Lake View", slug="lake-view")
    foreign_flat = Flat.objects.create(society=other, label="B-1")
    record_charge(society=other, flat=foreign_flat, amount=D("50.00"))

    with pytest.raises(ValidationError):
        record_payment(society=society, flat=foreign_flat, amount=D("10.00"), actor=treasurer)
    assert outstanding_for_flat(foreign_flat) == D("50.00")


# --- Idempotency (sequential) ---------------------------------------------------------------


@pytest.mark.django_db
def test_retry_with_same_key_returns_original_and_records_once():
    society, flat, treasurer = build_world("100.00")
    kwargs = dict(
        society=society, flat=flat, amount=D("30.00"), actor=treasurer, idempotency_key="k1"
    )

    first, first_created = record_payment(**kwargs)
    second, second_created = record_payment(**kwargs)

    assert (first_created, second_created) == (True, False)
    assert first.pk == second.pk
    assert outstanding_for_flat(flat) == D("70.00")  # charged once, not twice


@pytest.mark.django_db
def test_retry_still_succeeds_when_the_flat_is_now_fully_paid():
    """The key check must come BEFORE the overpayment check, or a retry would wrongly fail."""
    society, flat, treasurer = build_world("30.00")
    kwargs = dict(
        society=society, flat=flat, amount=D("30.00"), actor=treasurer, idempotency_key="k1"
    )
    record_payment(**kwargs)

    entry, created = record_payment(**kwargs)

    assert created is False


@pytest.mark.django_db
def test_same_key_with_a_different_request_is_a_conflict():
    society, flat, treasurer = build_world("100.00")
    record_payment(
        society=society, flat=flat, amount=D("30.00"), actor=treasurer, idempotency_key="k1"
    )

    with pytest.raises(IdempotencyKeyReused):
        record_payment(
            society=society, flat=flat, amount=D("40.00"), actor=treasurer, idempotency_key="k1"
        )
    other_flat = Flat.objects.create(society=society, label="A-102")
    record_charge(society=society, flat=other_flat, amount=D("100.00"))
    with pytest.raises(IdempotencyKeyReused):
        record_payment(
            society=society,
            flat=other_flat,
            amount=D("30.00"),
            actor=treasurer,
            idempotency_key="k1",
        )


# --- Concurrency: the guarantees this milestone exists to prove -------------------------------


@pytest.mark.django_db(transaction=True)
def test_parallel_payments_never_credit_more_than_is_owed(widen_race_window):
    """10 simultaneous payments of 30 against 100 owed: exactly 3 may succeed.

    Proves: the flat row lock turns check-then-act into a safe sequence. Without it all 10
    would read "owes 100", pass the check, and insert, leaving the flat 200 overpaid.
    """
    society, flat, treasurer = build_world("100.00")

    def pay(_):
        try:
            record_payment(society=society, flat=flat, amount=D("30.00"), actor=treasurer)
            return "ok"
        except PaymentExceedsOutstanding:
            return "rejected"

    results = run_in_parallel(10, pay)

    paid = sum(e.amount for e in LedgerEntry.objects.filter(flat=flat, kind="payment"))
    assert results.count("ok") == 3
    assert results.count("rejected") == 7
    assert paid == D("90.00")
    assert outstanding_for_flat(flat) == D("10.00")  # never negative


@pytest.mark.django_db(transaction=True)
def test_parallel_retries_with_one_key_record_exactly_one_payment(widen_race_window):
    """10 simultaneous submissions of the SAME request (a double click, a flaky-network retry).

    Proves: idempotency holds under concurrency: one entry, and every caller gets that entry.
    """
    society, flat, treasurer = build_world("100.00")

    def pay(_):
        entry, created = record_payment(
            society=society,
            flat=flat,
            amount=D("30.00"),
            actor=treasurer,
            idempotency_key="double-click",
        )
        return entry.pk, created

    results = run_in_parallel(10, pay)

    assert len({pk for pk, _ in results}) == 1
    assert [created for _, created in results].count(True) == 1
    assert LedgerEntry.objects.filter(kind="payment").count() == 1
    assert outstanding_for_flat(flat) == D("70.00")
