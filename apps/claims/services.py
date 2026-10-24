from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.audit import services as audit
from apps.audit.models import AuditLog
from apps.core.money import validate_amount
from apps.ledger.selectors import outstanding_for_flat
from apps.ledger.services import (
    IdempotencyKeyReused,
    check_flat_in_society,
    record_payment,
    refuse_own_flat,
)
from apps.societies.models import Flat, Membership

from .models import PaymentClaim

# A flat may have this many claims waiting at once. It stops a flood, and a resident with more
# than this has something to sort out with the treasurer, not through the app.
MAX_PENDING_PER_FLAT = 3
# A payment cannot have been made before this long ago. Catches a mistyped year.
MAX_AGE = timedelta(days=366)

# Shown on the resident's statement, so plain words rather than the stored codes.
METHOD_LABEL = {
    "upi": "UPI",
    "bank": "Bank transfer",
    "cash": "Cash",
    "cheque": "Cheque",
    "other": "Other",
}


class ClaimError(Exception):
    """Base class for expected, business-rule failures (the API maps these to 4xx)."""


class NotYourFlat(ClaimError):
    """Only someone who lives in the flat may say that the flat paid."""


class NotYourClaim(ClaimError):
    """Only the person who made a claim may withdraw it."""


class ClaimExceedsOutstanding(ClaimError):
    def __init__(self, outstanding):
        self.outstanding = outstanding
        super().__init__(f"The flat owes {outstanding}, which is less than the amount claimed.")


class TooManyPendingClaims(ClaimError):
    def __init__(self):
        super().__init__(
            f"This flat already has {MAX_PENDING_PER_FLAT} claims waiting. "
            "Wait for the treasurer to answer one first."
        )


class ClaimNotPending(ClaimError):
    """Already accepted, rejected or withdrawn: a claim is answered once."""

    def __init__(self, status):
        self.status = status
        super().__init__(f"This claim has already been {status}.")


def pending_count(flat) -> int:
    return PaymentClaim.objects.filter(flat=flat, status=PaymentClaim.Status.PENDING).count()


@transaction.atomic
def submit_claim(
    *, society, flat, claimant, amount, paid_on, method, reference="", idempotency_key=None
):
    """Record that a resident says their flat paid. Returns (claim, created). Touches no money.

    The flat row is locked first, the same lock record_payment takes. Two taps of "I've paid"
    (or two household members at once) then queue up, so the pending cap and the idempotency
    lookup both see the other request's committed row instead of racing past it.
    """
    validate_amount(amount)
    check_flat_in_society(society, flat)
    # The service checks this itself: the view's check is not the only door.
    if not Membership.objects.for_society(society).filter(user=claimant, flat=flat).exists():
        raise NotYourFlat("You can only report a payment for the flat you live in.")

    today = timezone.localdate()
    if paid_on > today:
        raise ValidationError({"paid_on": "The payment date cannot be in the future."})
    if paid_on < today - MAX_AGE:
        raise ValidationError({"paid_on": "That date is more than a year ago. Check the year."})

    flat = Flat.objects.for_society(society).select_for_update().get(pk=flat.pk)

    if idempotency_key:
        existing = PaymentClaim.objects.for_society(society).filter(
            idempotency_key=idempotency_key
        ).first()
        if existing is not None:
            same_request = (
                existing.claimed_by_id == claimant.pk
                and existing.flat_id == flat.pk
                and existing.amount == amount
                and existing.paid_on == paid_on
            )
            if not same_request:
                raise IdempotencyKeyReused(idempotency_key)
            return existing, False

    owed = outstanding_for_flat(flat)
    if amount > owed:
        raise ClaimExceedsOutstanding(owed)
    if pending_count(flat) >= MAX_PENDING_PER_FLAT:
        raise TooManyPendingClaims()

    try:
        with transaction.atomic():
            claim = PaymentClaim.objects.create(
                society=society,
                flat=flat,
                claimed_by=claimant,
                amount=amount,
                paid_on=paid_on,
                method=method,
                reference=reference.strip(),
                idempotency_key=idempotency_key or None,
            )
    except IntegrityError:
        if idempotency_key:
            raise IdempotencyKeyReused(idempotency_key) from None
        raise
    return claim, True


def _lock_pending(society, claim):
    """Lock the claim row and require that it is still waiting for an answer.

    Everything that answers a claim starts here. Two office-bearers acting on the same claim
    queue on this lock; the second finds it no longer pending and is refused. Lock order is
    always claim first, then flat (record_payment takes the flat lock itself), so two requests
    cannot wait on each other.
    """
    locked = (
        PaymentClaim.objects.for_society(society)
        .select_for_update(of=("self",))
        .get(pk=claim.pk)
    )
    if locked.status != PaymentClaim.Status.PENDING:
        raise ClaimNotPending(locked.status)
    return locked


@transaction.atomic
def accept_claim(*, society, claim, actor, amount=None, confirm_duplicate=False):
    """Record the payment a claim describes, and mark the claim accepted. All or nothing.

    `amount` lets the treasurer record what the bank really shows when it differs from what the
    resident said (the claim keeps both numbers). The payment goes through record_payment, so
    every rule applies unchanged: never more than is owed, never for the actor's own flat, and
    the duplicate warning if the same amount was just recorded by hand. If any of that refuses,
    nothing is written and the claim stays pending.

    The ledger entry carries the key "claim-<id>", so even if two requests got past the claim
    lock, the ledger's own idempotency rule would still record the payment once.
    """
    claim = _lock_pending(society, claim)
    flat = Flat.objects.for_society(society).get(pk=claim.flat_id)
    recorded = claim.amount if amount is None else amount

    entry, _created = record_payment(
        society=society,
        flat=flat,
        amount=recorded,
        actor=actor,
        idempotency_key=f"claim-{claim.pk}",
        note=f"Reported by resident: {METHOD_LABEL[claim.method]} {claim.reference}".strip()[:200],
        confirm_duplicate=confirm_duplicate,
    )

    claim.status = PaymentClaim.Status.ACCEPTED
    claim.resolved_by = actor
    claim.resolved_at = timezone.now()
    claim.accepted_amount = recorded
    claim.ledger_entry = entry
    claim.save(
        update_fields=["status", "resolved_by", "resolved_at", "accepted_amount", "ledger_entry"]
    )
    audit.record(
        society=society,
        actor=actor,
        action=AuditLog.Action.CLAIM_ACCEPTED,
        flat=flat,
        object_type="payment_claim",
        object_id=claim.pk,
        amount=recorded,
        data={"claimed": str(claim.amount), "recorded": str(recorded), "entry": entry.pk},
    )
    return claim


@transaction.atomic
def reject_claim(*, society, claim, actor, reason):
    """Turn a claim down, with a reason the resident will read. The ledger is untouched."""
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError({"reason": "Say why, so the resident knows what to do next."})
    if len(reason) > 200:
        raise ValidationError({"reason": "Keep the reason under 200 characters."})

    claim = _lock_pending(society, claim)
    # Whoever lives in the flat must not be the one who answers for it.
    refuse_own_flat(society, actor, claim.flat_id)

    claim.status = PaymentClaim.Status.REJECTED
    claim.resolved_by = actor
    claim.resolved_at = timezone.now()
    claim.resolution_note = reason
    claim.save(update_fields=["status", "resolved_by", "resolved_at", "resolution_note"])
    audit.record(
        society=society,
        actor=actor,
        action=AuditLog.Action.CLAIM_REJECTED,
        flat=claim.flat,
        object_type="payment_claim",
        object_id=claim.pk,
        amount=claim.amount,
        data={"claimed": str(claim.amount)},
    )
    return claim


@transaction.atomic
def withdraw_claim(*, society, claim, actor):
    """The resident takes their own pending claim back (a mistake, or they paid another way)."""
    claim = _lock_pending(society, claim)
    if claim.claimed_by_id != actor.pk:
        raise NotYourClaim("Only the person who made this claim can withdraw it.")

    claim.status = PaymentClaim.Status.WITHDRAWN
    claim.resolved_at = timezone.now()
    claim.save(update_fields=["status", "resolved_at"])
    return claim
