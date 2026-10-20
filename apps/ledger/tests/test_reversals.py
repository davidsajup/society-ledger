from decimal import Decimal

import pytest

from apps.ledger.models import LedgerEntry
from apps.ledger.selectors import outstanding_for_flat
from apps.ledger.services import (
    PaymentExceedsOutstanding,
    ReversalNotAllowed,
    record_charge,
    record_payment,
    reverse_entry,
)
from apps.ledger.tests.helpers import build_world, run_in_parallel
from apps.societies.models import Flat, Society

D = Decimal


@pytest.mark.django_db
def test_reversing_a_payment_restores_what_is_owed_and_keeps_history():
    society, flat, treasurer = build_world("100.00")
    payment, _ = record_payment(society=society, flat=flat, amount=D("100.00"), actor=treasurer)

    reversal = reverse_entry(society=society, entry=payment, actor=treasurer, note="bounced")

    assert (reversal.kind, reversal.amount, reversal.reverses) == ("charge", D("100.00"), payment)
    assert outstanding_for_flat(flat) == D("100.00")
    assert LedgerEntry.objects.filter(flat=flat).count() == 3  # nothing was edited or removed


@pytest.mark.django_db
def test_reversing_an_unpaid_charge_cancels_it():
    society, flat, treasurer = build_world(owed=None)
    charge = record_charge(society=society, flat=flat, amount=D("40.00"))

    reversal = reverse_entry(society=society, entry=charge, actor=treasurer)

    assert reversal.kind == "payment"
    assert outstanding_for_flat(flat) == D("0.00")


@pytest.mark.django_db
def test_an_entry_cannot_be_reversed_twice():
    society, flat, treasurer = build_world("100.00")
    payment, _ = record_payment(society=society, flat=flat, amount=D("30.00"), actor=treasurer)
    reverse_entry(society=society, entry=payment, actor=treasurer)

    with pytest.raises(ReversalNotAllowed, match="already been reversed"):
        reverse_entry(society=society, entry=payment, actor=treasurer)
    assert outstanding_for_flat(flat) == D("100.00")


@pytest.mark.django_db
def test_a_reversal_cannot_itself_be_reversed():
    society, flat, treasurer = build_world("100.00")
    payment, _ = record_payment(society=society, flat=flat, amount=D("30.00"), actor=treasurer)
    reversal = reverse_entry(society=society, entry=payment, actor=treasurer)

    with pytest.raises(ReversalNotAllowed, match="cannot itself"):
        reverse_entry(society=society, entry=reversal, actor=treasurer)


@pytest.mark.django_db
def test_a_paid_charge_cannot_be_reversed_until_the_payment_is():
    """Reversing a fully paid charge would leave the flat in credit, which we do not allow."""
    society, flat, treasurer = build_world(owed=None)
    charge = record_charge(society=society, flat=flat, amount=D("100.00"))
    payment, _ = record_payment(society=society, flat=flat, amount=D("100.00"), actor=treasurer)

    with pytest.raises(ReversalNotAllowed, match="reverse the payments first"):
        reverse_entry(society=society, entry=charge, actor=treasurer)

    reverse_entry(society=society, entry=payment, actor=treasurer)  # now owes 100 again
    reverse_entry(society=society, entry=charge, actor=treasurer)  # allowed
    assert outstanding_for_flat(flat) == D("0.00")


@pytest.mark.django_db
def test_an_entry_of_another_society_cannot_be_reversed():
    society, _, treasurer = build_world()
    other = Society.objects.create(name="Lake View", slug="lake-view")
    foreign_flat = Flat.objects.create(society=other, label="B-1")
    foreign_charge = record_charge(society=other, flat=foreign_flat, amount=D("50.00"))

    with pytest.raises(LedgerEntry.DoesNotExist):
        reverse_entry(society=society, entry=foreign_charge, actor=treasurer)
    assert outstanding_for_flat(foreign_flat) == D("50.00")


@pytest.mark.django_db(transaction=True)
def test_parallel_reversals_of_one_payment_succeed_exactly_once(widen_race_window):
    """Proves: a payment cannot be reversed twice even if two requests arrive together."""
    society, flat, treasurer = build_world("100.00")
    payment, _ = record_payment(society=society, flat=flat, amount=D("100.00"), actor=treasurer)

    def reverse(_):
        try:
            reverse_entry(society=society, entry=payment, actor=treasurer)
            return "ok"
        except ReversalNotAllowed:
            return "rejected"

    results = run_in_parallel(6, reverse)

    assert results.count("ok") == 1
    assert LedgerEntry.objects.filter(reverses=payment).count() == 1
    assert outstanding_for_flat(flat) == D("100.00")


@pytest.mark.django_db(transaction=True)
def test_payment_racing_a_charge_reversal_never_leaves_the_flat_in_credit(widen_race_window):
    """Flat owes 100. One request pays 100, another reverses the 100 charge, at the same time.

    Proves: both go through the same flat lock, so exactly one wins. Without the lock both
    would pass their own check and the flat would end at -100 (credit we never allowed).
    """
    society, flat, treasurer = build_world(owed=None)
    charge = record_charge(society=society, flat=flat, amount=D("100.00"))

    def act(i):
        try:
            if i == 0:
                record_payment(society=society, flat=flat, amount=D("100.00"), actor=treasurer)
            else:
                reverse_entry(society=society, entry=charge, actor=treasurer)
            return "ok"
        except (PaymentExceedsOutstanding, ReversalNotAllowed):
            return "rejected"

    results = run_in_parallel(2, act)

    assert sorted(results) == ["ok", "rejected"]
    assert outstanding_for_flat(flat) == D("0.00")
