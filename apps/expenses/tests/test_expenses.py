from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.core.append_only import AppendOnlyError
from apps.expenses.models import Expense
from apps.expenses.selectors import total_spent
from apps.expenses.services import (
    ExpenseNotReversible,
    IdempotencyKeyReused,
    record_expense,
    reverse_expense,
)
from apps.ledger.tests.helpers import run_in_parallel
from apps.societies.models import Society

D = Decimal


def world():
    society = Society.objects.create(name="Green Park", slug="green-park")
    treasurer = get_user_model().objects.create_user(username="treasurer", password="x")
    return society, treasurer


def spend(society, treasurer, amount="100.00", **extra):
    if isinstance(amount, str):
        amount = D(amount)  # Decimals and floats are passed through untouched, to test them
    fields = dict(
        category="utilities", description="Electricity", amount=amount,
        paid_on=timezone.localdate(),
    )
    fields.update(extra)
    return record_expense(society=society, actor=treasurer, **fields)


@pytest.mark.django_db
def test_recording_an_expense_stores_it_audits_it_and_counts_it():
    society, treasurer = world()

    expense, created = spend(society, treasurer, "250.50")

    assert created is True
    assert (expense.created_by, expense.amount) == (treasurer, D("250.50"))
    assert total_spent(society) == D("250.50")
    row = AuditLog.objects.get(action="expense.recorded")
    assert (row.object_id, row.amount) == (expense.pk, D("250.50"))
    assert row.data == {"category": "utilities"}


@pytest.mark.django_db
def test_total_is_exact_and_zero_when_empty():
    society, treasurer = world()
    assert total_spent(society) == D("0.00")

    spend(society, treasurer, "0.10")
    spend(society, treasurer, "0.20")

    assert total_spent(society) == D("0.30")


@pytest.mark.django_db
@pytest.mark.parametrize(
    "bad", [D("0"), D("-5.00"), D("1.005"), D("NaN")], ids=["zero", "negative", "3dp", "nan"]
)
def test_bad_amounts_are_rejected(bad):
    society, treasurer = world()
    with pytest.raises(ValidationError):
        spend(society, treasurer, bad)
    assert not Expense.objects.exists()


@pytest.mark.django_db
def test_floats_unknown_categories_and_future_dates_are_rejected():
    society, treasurer = world()
    with pytest.raises(TypeError):
        spend(society, treasurer, 12.5)
    with pytest.raises(ValidationError):
        spend(society, treasurer, category="yacht")
    with pytest.raises(ValidationError):
        spend(society, treasurer, paid_on=timezone.localdate() + timedelta(days=1))
    assert not Expense.objects.exists()
    assert not AuditLog.objects.exists()


# --- Idempotency ----------------------------------------------------------------------------


@pytest.mark.django_db
def test_retry_with_same_key_returns_original_and_records_once():
    society, treasurer = world()
    day = date(2026, 10, 3)

    first, c1 = spend(society, treasurer, idempotency_key="k1", paid_on=day)
    second, c2 = spend(society, treasurer, idempotency_key="k1", paid_on=day)

    assert (c1, c2) == (True, False)
    assert first.pk == second.pk
    assert Expense.objects.count() == 1
    assert AuditLog.objects.filter(action="expense.recorded").count() == 1


@pytest.mark.django_db
def test_same_key_with_a_different_request_is_a_conflict():
    society, treasurer = world()
    spend(society, treasurer, "100.00", idempotency_key="k1")

    with pytest.raises(IdempotencyKeyReused):
        spend(society, treasurer, "999.00", idempotency_key="k1")


@pytest.mark.django_db(transaction=True)
def test_ten_simultaneous_identical_submissions_record_exactly_one_expense():
    """Proves: a double click / retry storm cannot double the spending.

    No row lock is used here: the unique idempotency key decides the race and the losers read
    the winner's row back.
    """
    society, treasurer = world()
    day = date(2026, 10, 3)

    results = run_in_parallel(
        10,
        lambda _: record_expense(
            society=society, actor=treasurer, category="repairs", description="Lift motor",
            amount=D("5000.00"), paid_on=day, idempotency_key="double-click",
        ),
    )

    assert [created for _, created in results].count(True) == 1
    assert len({expense.pk for expense, _ in results}) == 1
    assert Expense.objects.count() == 1
    assert AuditLog.objects.filter(action="expense.recorded").count() == 1
    assert total_spent(society) == D("5000.00")


# --- Reversals ------------------------------------------------------------------------------


@pytest.mark.django_db
def test_reversing_an_expense_cancels_it_in_the_total_and_keeps_history():
    society, treasurer = world()
    expense, _ = spend(society, treasurer, "400.00")

    reversal = reverse_expense(society=society, expense=expense, actor=treasurer)

    assert reversal.reverses == expense
    assert total_spent(society) == D("0.00")
    assert Expense.objects.count() == 2
    assert AuditLog.objects.filter(action="expense.reversed").count() == 1


@pytest.mark.django_db
def test_an_expense_cannot_be_reversed_twice_and_a_reversal_cannot_be_reversed():
    society, treasurer = world()
    expense, _ = spend(society, treasurer)
    reversal = reverse_expense(society=society, expense=expense, actor=treasurer)

    with pytest.raises(ExpenseNotReversible, match="already been reversed"):
        reverse_expense(society=society, expense=expense, actor=treasurer)
    with pytest.raises(ExpenseNotReversible, match="cannot itself"):
        reverse_expense(society=society, expense=reversal, actor=treasurer)
    assert total_spent(society) == D("0.00")


@pytest.mark.django_db
def test_an_expense_of_another_society_cannot_be_reversed():
    society, treasurer = world()
    other = Society.objects.create(name="Lake View", slug="lake-view")
    foreign, _ = spend(other, treasurer, "50.00")

    with pytest.raises(Expense.DoesNotExist):
        reverse_expense(society=society, expense=foreign, actor=treasurer)
    assert total_spent(other) == D("50.00")


@pytest.mark.django_db(transaction=True)
def test_parallel_reversals_succeed_exactly_once():
    society, treasurer = world()
    expense, _ = spend(society, treasurer, "75.00")

    def reverse(_):
        try:
            reverse_expense(society=society, expense=expense, actor=treasurer)
            return "ok"
        except ExpenseNotReversible:
            return "rejected"

    results = run_in_parallel(6, reverse)

    assert results.count("ok") == 1
    assert Expense.objects.filter(reverses=expense).count() == 1
    assert total_spent(society) == D("0.00")


# --- Append-only and tenant scoping ---------------------------------------------------------


@pytest.mark.django_db
def test_expenses_cannot_be_edited_or_deleted_through_the_orm():
    society, treasurer = world()
    expense, _ = spend(society, treasurer)

    expense.amount = D("1.00")
    with pytest.raises(AppendOnlyError):
        expense.save()
    with pytest.raises(AppendOnlyError):
        expense.delete()
    with pytest.raises(AppendOnlyError):
        Expense.objects.all().update(amount=D("1.00"))


@pytest.mark.django_db
@pytest.mark.parametrize(
    "sql", ["UPDATE expenses_expense SET amount = 1", "DELETE FROM expenses_expense"]
)
def test_expenses_cannot_be_edited_or_deleted_with_raw_sql(sql):
    society, treasurer = world()
    spend(society, treasurer)

    with pytest.raises(IntegrityError, match="append-only"), transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(sql)
    assert Expense.objects.count() == 1


@pytest.mark.django_db
def test_database_rejects_a_non_positive_amount():
    society, treasurer = world()
    with pytest.raises(IntegrityError), transaction.atomic():
        Expense.objects.create(
            society=society, category="other", description="x", amount=D("0"),
            paid_on=date(2026, 11, 1), created_by=treasurer,
        )


@pytest.mark.django_db
def test_total_spent_only_counts_this_society():
    society, treasurer = world()
    other = Society.objects.create(name="Lake View", slug="lake-view")
    spend(society, treasurer, "10.00")
    spend(other, treasurer, "9999.00")

    assert total_spent(society) == D("10.00")
