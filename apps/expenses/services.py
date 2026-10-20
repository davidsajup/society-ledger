from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.audit import services as audit
from apps.audit.models import AuditLog
from apps.core.money import validate_amount

from .models import Expense


class ExpenseError(Exception):
    """Base class for expected, business-rule failures (the API maps these to 4xx)."""


class ExpenseNotReversible(ExpenseError):
    """Already reversed, or is itself a reversal."""


class IdempotencyKeyReused(ExpenseError):
    """The same key was sent with a different request, which is a client bug."""


def _same_request(existing, *, category, description, amount, paid_on):
    return (
        existing.reverses_id is None
        and existing.category == category
        and existing.description == description
        and existing.amount == amount
        and existing.paid_on == paid_on
    )


@transaction.atomic
def record_expense(
    *, society, actor, category, description, amount, paid_on, idempotency_key=None
):
    """Append an expense. Returns (expense, created).

    There is no balance to protect here, so no row lock: the unique constraint on the
    idempotency key decides a race, and the loser reads the winner's row back. A retry with the
    same key returns the original; the same key with a different request is a conflict.
    """
    validate_amount(amount)
    if category not in Expense.Category.values:
        raise ValidationError("Unknown category.")
    if paid_on > timezone.localdate():
        raise ValidationError("An expense cannot be dated in the future.")
    request = dict(category=category, description=description, amount=amount, paid_on=paid_on)

    def replay():
        existing = (
            Expense.objects.for_society(society).filter(idempotency_key=idempotency_key).first()
        )
        if existing is None:
            return None
        if not _same_request(existing, **request):
            raise IdempotencyKeyReused(idempotency_key)
        return existing, False

    if idempotency_key and (found := replay()):
        return found

    try:
        with transaction.atomic():  # savepoint, so a clash does not poison the outer transaction
            expense = Expense.objects.create(
                society=society,
                created_by=actor,
                idempotency_key=idempotency_key or None,
                **request,
            )
    except IntegrityError:
        if idempotency_key and (found := replay()):
            return found  # lost the race to an identical request: hand back its row
        raise

    audit.record(
        society=society,
        actor=actor,
        action=AuditLog.Action.EXPENSE_RECORDED,
        object_type="expense",
        object_id=expense.pk,
        amount=amount,
        data={"category": category},
    )
    return expense, True


@transaction.atomic
def reverse_expense(*, society, expense, actor):
    """Correct a mistaken expense by appending its opposite. At most once; not a reversal's."""
    original = Expense.objects.for_society(society).get(pk=expense.pk)
    if original.reverses_id is not None:
        raise ExpenseNotReversible("A reversal cannot itself be reversed.")

    try:
        with transaction.atomic():
            reversal = Expense.objects.create(
                society=society,
                category=original.category,
                description=f"Reversal: {original.description}"[:200],
                amount=original.amount,
                paid_on=timezone.localdate(),
                created_by=actor,
                reverses=original,
            )
    except IntegrityError:
        # The OneToOne on `reverses` refused a second reversal (also covers two racing requests).
        raise ExpenseNotReversible("This expense has already been reversed.") from None

    audit.record(
        society=society,
        actor=actor,
        action=AuditLog.Action.EXPENSE_REVERSED,
        object_type="expense",
        object_id=reversal.pk,
        amount=reversal.amount,
        data={"reverses": original.pk, "category": original.category},
    )
    return reversal
