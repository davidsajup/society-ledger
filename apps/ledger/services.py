from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.audit import services as audit
from apps.audit.models import AuditLog
from apps.core.money import validate_amount
from apps.societies.models import Flat

from .models import LedgerEntry
from .selectors import outstanding_for_flat


class LedgerError(Exception):
    """Base class for expected, business-rule failures (the API maps these to 4xx)."""


class PaymentExceedsOutstanding(LedgerError):
    def __init__(self, outstanding):
        self.outstanding = outstanding
        super().__init__(f"Payment exceeds the amount owed ({outstanding}).")


class ReversalNotAllowed(LedgerError):
    """Already reversed, is itself a reversal, or reversing it would leave the flat in credit."""


class IdempotencyKeyReused(LedgerError):
    """The same key was sent with a different request, which is a client bug."""


def check_flat_in_society(society, flat):
    # The DB cannot express "flat belongs to this society" (no composite foreign keys).
    if flat.society_id != society.id:
        raise ValidationError("Flat belongs to a different society.")


def record_charge(*, society, flat, amount, actor=None, note="", billing_run=None):
    """Append a charge: the flat now owes `amount` more.

    Used by the M3 billing job and by tests. There is deliberately no HTTP endpoint for it.
    No flat lock is needed: a charge only ever increases what is owed, so it cannot break the
    "never overpaid" rule that the lock protects.
    """
    validate_amount(amount)
    check_flat_in_society(society, flat)
    return LedgerEntry.objects.create(
        society=society,
        flat=flat,
        kind=LedgerEntry.Kind.CHARGE,
        amount=amount,
        created_by=actor,
        note=note,
        billing_run=billing_run,
    )


@transaction.atomic
def record_payment(*, society, flat, amount, actor, idempotency_key=None, note=""):
    """Append a payment for `flat`. Returns (entry, created).

    Guarantees:
    * never records more than the flat owes, even under concurrent requests;
    * a retry with the same idempotency_key returns the original entry (created=False)
      instead of recording the payment twice.

    How: lock the flat row first. Every payment for this flat then waits its turn, and because
    Postgres runs at READ COMMITTED, the balance recomputed AFTER the lock sees every payment
    that committed while we waited. Without the lock, two requests could both read "owes 100",
    both pass the check, and both insert (check-then-act race).
    """
    validate_amount(amount)
    check_flat_in_society(society, flat)

    # The lock. Re-fetching through for_society() also guarantees the flat is in this society.
    flat = Flat.objects.for_society(society).select_for_update().get(pk=flat.pk)

    if idempotency_key:
        # Looked up by society (not flat) so a key reused on another flat is also caught.
        existing = LedgerEntry.objects.for_society(society).filter(
            idempotency_key=idempotency_key
        ).first()
        if existing is not None:
            same_request = (
                existing.kind == LedgerEntry.Kind.PAYMENT
                and existing.flat_id == flat.id
                and existing.amount == amount
            )
            if not same_request:
                raise IdempotencyKeyReused(idempotency_key)
            return existing, False

    owed = outstanding_for_flat(flat)
    if amount > owed:
        raise PaymentExceedsOutstanding(owed)

    try:
        with transaction.atomic():  # savepoint, so a clash does not poison the outer transaction
            entry = LedgerEntry.objects.create(
                society=society,
                flat=flat,
                kind=LedgerEntry.Kind.PAYMENT,
                amount=amount,
                created_by=actor,
                note=note,
                idempotency_key=idempotency_key or None,
            )
    except IntegrityError:
        if idempotency_key:
            # Same key used for a different flat at the same moment (the flat lock cannot
            # serialize those two requests).
            raise IdempotencyKeyReused(idempotency_key) from None
        raise

    # Same transaction as the entry above: both commit, or neither does. Replays (returned
    # earlier) are not new actions, so they write no audit row.
    audit.record(
        society=society,
        actor=actor,
        action=AuditLog.Action.PAYMENT_RECORDED,
        flat=flat,
        object_type="ledger_entry",
        object_id=entry.pk,
        amount=amount,
        data={"idempotency_key": idempotency_key} if idempotency_key else {},
    )
    return entry, True


@transaction.atomic
def reverse_entry(*, society, entry, actor, note=""):
    """Correct a mistake by appending the opposite entry. Nothing is ever edited or deleted.

    Reversing a payment appends a charge (the flat owes again); reversing a charge appends a
    payment. Rules, all checked while holding the flat lock:
    * an entry is reversed at most once, and a reversal cannot itself be reversed;
    * a charge cannot be reversed if the flat has already paid it (that would create credit):
      reverse the payments first.
    """
    # Looked up through for_society(): an entry of another society is simply not found.
    original = LedgerEntry.objects.for_society(society).get(pk=entry.pk)
    flat = Flat.objects.for_society(society).select_for_update().get(pk=original.flat_id)

    if original.reverses_id is not None:
        raise ReversalNotAllowed("A reversal cannot itself be reversed.")
    if LedgerEntry.objects.for_society(society).filter(reverses=original).exists():
        raise ReversalNotAllowed("This entry has already been reversed.")

    if original.kind == LedgerEntry.Kind.CHARGE:
        if original.amount > outstanding_for_flat(flat):
            raise ReversalNotAllowed(
                "The flat has already paid this charge; reverse the payments first."
            )
        opposite = LedgerEntry.Kind.PAYMENT
    else:
        opposite = LedgerEntry.Kind.CHARGE

    try:
        with transaction.atomic():
            reversal = LedgerEntry.objects.create(
                society=society,
                flat=flat,
                kind=opposite,
                amount=original.amount,
                created_by=actor,
                note=note,
                reverses=original,
            )
    except IntegrityError:
        # Backstop: the OneToOne on `reverses` refused a second reversal.
        raise ReversalNotAllowed("This entry has already been reversed.") from None

    audit.record(
        society=society,
        actor=actor,
        action=AuditLog.Action.ENTRY_REVERSED,
        flat=flat,
        object_type="ledger_entry",
        object_id=reversal.pk,
        amount=reversal.amount,
        data={"reverses": original.pk, "original_kind": original.kind},
    )
    return reversal
