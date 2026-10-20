from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.models import ProtectedError

from apps.ledger.models import AppendOnlyError, LedgerEntry
from apps.ledger.selectors import outstanding_for_flat
from apps.ledger.services import record_charge
from apps.societies.models import Flat, Society

pytestmark = pytest.mark.django_db

D = Decimal


@pytest.fixture
def society():
    return Society.objects.create(name="Green Park", slug="green-park")


@pytest.fixture
def other_society():
    return Society.objects.create(name="Lake View", slug="lake-view")


@pytest.fixture
def flat(society):
    return Flat.objects.create(society=society, label="A-101")


def make_entry(society, flat, kind="charge", amount="100.00", **extra):
    return LedgerEntry.objects.create(
        society=society, flat=flat, kind=kind, amount=D(amount), **extra
    )


# --- Money rules enforced by the database ---------------------------------------------------


@pytest.mark.parametrize("bad", ["0.00", "-5.00"])
def test_database_rejects_non_positive_amounts(society, flat, bad):
    with pytest.raises(IntegrityError), transaction.atomic():
        make_entry(society, flat, amount=bad)


def test_database_rejects_unknown_kind(society, flat):
    with pytest.raises(IntegrityError), transaction.atomic():
        make_entry(society, flat, kind="refund")


def test_idempotency_key_is_unique_within_a_society(society, flat):
    make_entry(society, flat, idempotency_key="abc")
    with pytest.raises(IntegrityError), transaction.atomic():
        make_entry(society, flat, idempotency_key="abc")


def test_idempotency_key_may_repeat_across_societies_and_be_absent(
    society, other_society, flat
):
    other_flat = Flat.objects.create(society=other_society, label="B-1")
    make_entry(society, flat, idempotency_key="abc")
    make_entry(other_society, other_flat, idempotency_key="abc")  # other tenant: allowed
    make_entry(society, flat)  # no key
    make_entry(society, flat)  # no key again: allowed


def test_an_entry_can_be_reversed_only_once(society, flat):
    original = make_entry(society, flat, kind="payment", amount="30.00")
    make_entry(society, flat, kind="charge", amount="30.00", reverses=original)
    with pytest.raises(IntegrityError), transaction.atomic():
        make_entry(society, flat, kind="charge", amount="30.00", reverses=original)


def test_flat_with_ledger_history_cannot_be_deleted(society, flat):
    make_entry(society, flat)
    with pytest.raises(ProtectedError):
        flat.delete()


# --- Append-only: Python guard --------------------------------------------------------------


def test_orm_save_on_existing_entry_is_refused(society, flat):
    entry = make_entry(society, flat)
    entry.note = "edited"
    with pytest.raises(AppendOnlyError):
        entry.save()


def test_orm_delete_is_refused(society, flat):
    entry = make_entry(society, flat)
    with pytest.raises(AppendOnlyError):
        entry.delete()


def test_queryset_update_and_delete_are_refused(society, flat):
    make_entry(society, flat)
    with pytest.raises(AppendOnlyError):
        LedgerEntry.objects.all().update(note="x")
    with pytest.raises(AppendOnlyError):
        LedgerEntry.objects.all().delete()


# --- Append-only: Postgres trigger (raw SQL bypasses the ORM entirely) ------------------------


def test_raw_sql_update_is_refused_by_postgres(society, flat):
    make_entry(society, flat)
    with pytest.raises(IntegrityError, match="append-only"), transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("UPDATE ledger_ledgerentry SET amount = 1")


def test_raw_sql_delete_is_refused_by_postgres(society, flat):
    make_entry(society, flat)
    with pytest.raises(IntegrityError, match="append-only"), transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM ledger_ledgerentry")
    assert LedgerEntry.objects.count() == 1


# --- Balance --------------------------------------------------------------------------------


def test_empty_ledger_owes_exactly_zero(flat):
    assert outstanding_for_flat(flat) == D("0.00")
    assert isinstance(outstanding_for_flat(flat), Decimal)


def test_balance_is_charges_minus_payments(society, flat):
    make_entry(society, flat, kind="charge", amount="100.00")
    make_entry(society, flat, kind="payment", amount="30.00")

    assert outstanding_for_flat(flat) == D("70.00")


def test_balance_is_exact_where_floats_are_not(society, flat):
    """0.10 + 0.20 == 0.30000000000000004 as floats. The ledger must give exactly 0.30."""
    assert 0.1 + 0.2 != 0.3
    make_entry(society, flat, amount="0.10")
    make_entry(society, flat, amount="0.20")

    assert outstanding_for_flat(flat) == D("0.30")


def test_balance_ignores_other_flats_and_other_societies(society, other_society, flat):
    sibling = Flat.objects.create(society=society, label="A-102")
    foreign = Flat.objects.create(society=other_society, label="A-101")
    make_entry(society, flat, amount="50.00")
    make_entry(society, sibling, amount="999.00")
    make_entry(other_society, foreign, amount="777.00")

    assert outstanding_for_flat(flat) == D("50.00")


def test_a_reversed_payment_restores_what_is_owed(society, flat):
    make_entry(society, flat, kind="charge", amount="100.00")
    payment = make_entry(society, flat, kind="payment", amount="100.00")
    make_entry(society, flat, kind="charge", amount="100.00", reverses=payment)

    assert outstanding_for_flat(flat) == D("100.00")


# --- record_charge service ------------------------------------------------------------------


def test_record_charge_creates_a_charge(society, flat):
    actor = get_user_model().objects.create_user(username="t", password="x")
    entry = record_charge(society=society, flat=flat, amount=D("250.00"), actor=actor)

    assert (entry.kind, entry.amount, entry.created_by) == ("charge", D("250.00"), actor)


def test_record_charge_rejects_floats(society, flat):
    with pytest.raises(TypeError):
        record_charge(society=society, flat=flat, amount=250.0)


@pytest.mark.parametrize("bad", [D("0"), D("-1.00"), D("1.005"), D("NaN"), D("Infinity")])
def test_record_charge_rejects_bad_amounts(society, flat, bad):
    with pytest.raises(ValidationError):
        record_charge(society=society, flat=flat, amount=bad)
    assert not LedgerEntry.objects.exists()


def test_record_charge_rejects_flat_from_another_society(society, other_society):
    foreign = Flat.objects.create(society=other_society, label="B-1")
    with pytest.raises(ValidationError):
        record_charge(society=society, flat=foreign, amount=D("10.00"))
