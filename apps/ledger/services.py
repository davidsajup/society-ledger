from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.audit import services as audit
from apps.audit.models import AuditLog
from apps.core.money import validate_amount
from apps.societies.models import Flat, Membership

from .models import LedgerEntry
from .selectors import outstanding_for_flat


class LedgerError(Exception):
    """Base class for expected, business-rule failures (the API maps these to 4xx)."""


class PaymentExceedsOutstanding(LedgerError):
    def __init__(self, outstanding):
        self.outstanding = outstanding
        super().__init__(f"Payment exceeds the amount owed ({outstanding}).")


# How far back a payment of the same amount on the same flat counts as "probably the same one".
DUPLICATE_WINDOW = timedelta(minutes=10)


class PossibleDuplicatePayment(LedgerError):
    """The same amount was recorded for this flat moments ago; the caller must confirm."""

    def __init__(self, previous):
        self.previous = previous
        super().__init__("A payment of this amount was just recorded for this flat.")


class SelfPaymentNotAllowed(LedgerError):
    """The actor lives in this flat, so someone else must record or reverse its payments."""


class ReversalNotAllowed(LedgerError):
    """Already reversed, is itself a reversal, or reversing it would leave the flat in credit."""


class IdempotencyKeyReused(LedgerError):
    """The same key was sent with a different request, which is a client bug."""


def refuse_own_flat(society, actor, flat_id):
    """Segregation of duties: nobody may record or reverse payments for the flat they live in.

    Office-bearers are also residents who pay dues. If the treasurer could mark their own flat
    as paid (or cancel their own charge), the person being credited would be the person doing
    the crediting. Another office-bearer must do it. Applies to every role, and to anyone who
    shares the flat. The check is on the ACTOR's membership, so it cannot be skipped by
    choosing a different flat id.
    """
    if actor is None:  # system jobs have no actor and no flat
        return
    if Membership.objects.for_society(society).filter(user=actor, flat_id=flat_id).exists():
        raise SelfPaymentNotAllowed(
            "You cannot record or reverse a payment for the flat you live in. "
            "Ask another office-bearer to do it."
        )


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


def find_recent_duplicate(society, flat, amount):
    """A live payment of exactly `amount` on this flat inside DUPLICATE_WINDOW, or None.

    "Live" means not reversed and not itself a reversal: once someone has corrected a payment,
    re-recording the right one must not be questioned.
    """
    return (
        LedgerEntry.objects.for_society(society)
        .filter(
            flat=flat,
            kind=LedgerEntry.Kind.PAYMENT,
            amount=amount,
            reverses__isnull=True,
            reversed_by__isnull=True,
            created_at__gte=timezone.now() - DUPLICATE_WINDOW,
        )
        .order_by("-created_at", "-id")
        .first()
    )


@transaction.atomic
def record_payment(
    *, society, flat, amount, actor, idempotency_key=None, note="", confirm_duplicate=False
):
    """Append a payment for `flat`. Returns (entry, created).

    Guarantees:
    * never records more than the flat owes, even under concurrent requests;
    * a retry with the same idempotency_key returns the original entry (created=False)
      instead of recording the payment twice;
    * the same amount on the same flat within DUPLICATE_WINDOW is refused with
      PossibleDuplicatePayment unless `confirm_duplicate` is true. This catches what the key
      cannot: a person starting over (new form, new key) after a reply was lost.

    How: lock the flat row first. Every payment for this flat then waits its turn, and because
    Postgres runs at READ COMMITTED, the balance recomputed AFTER the lock sees every payment
    that committed while we waited. Without the lock, two requests could both read "owes 100",
    both pass the check, and both insert (check-then-act race).
    """
    validate_amount(amount)
    check_flat_in_society(society, flat)
    refuse_own_flat(society, actor, flat.pk)

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

    # After the lock, so two simultaneous submissions queue and the second sees the first.
    duplicate = find_recent_duplicate(society, flat, amount)
    if duplicate is not None and not confirm_duplicate:
        raise PossibleDuplicatePayment(duplicate)

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
    audit_data = {}
    if idempotency_key:
        audit_data["idempotency_key"] = idempotency_key
    if duplicate is not None:  # only reachable with confirm_duplicate: the override is on record
        audit_data["confirmed_duplicate_of"] = duplicate.pk
    audit.record(
        society=society,
        actor=actor,
        action=AuditLog.Action.PAYMENT_RECORDED,
        flat=flat,
        object_type="ledger_entry",
        object_id=entry.pk,
        amount=amount,
        data=audit_data,
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
    refuse_own_flat(society, actor, original.flat_id)
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
