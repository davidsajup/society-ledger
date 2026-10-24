from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.tenancy import TenantQuerySet


class PaymentClaim(models.Model):
    """A resident's note to the treasurer: "I paid this". It is NOT money.

    The ledger changes only when an office-bearer accepts the claim, and that goes through the
    normal record_payment path (locks, overpayment check, audit). Until then, and forever if it
    is rejected or withdrawn, the claim never touches a balance.

    Unlike the ledger a claim moves through states (pending -> accepted / rejected /
    withdrawn), and the constraints below make an impossible combination unstorable: an
    accepted claim must point at the payment it produced, a rejected one must say why, and a
    pending one has no resolver.
    """

    class Status(models.TextChoices):
        PENDING = "pending"
        ACCEPTED = "accepted"
        REJECTED = "rejected"
        WITHDRAWN = "withdrawn"

    class Method(models.TextChoices):
        UPI = "upi"
        BANK = "bank"
        CASH = "cash"
        CHEQUE = "cheque"
        OTHER = "other"

    society = models.ForeignKey(
        "societies.Society", on_delete=models.PROTECT, related_name="payment_claims"
    )
    flat = models.ForeignKey(
        "societies.Flat", on_delete=models.PROTECT, related_name="payment_claims"
    )
    claimed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    paid_on = models.DateField()
    method = models.CharField(max_length=10, choices=Method.choices)
    reference = models.CharField(max_length=60, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)

    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
        related_name="+",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    # Why a claim was rejected. Shown to the resident.
    resolution_note = models.CharField(max_length=200, blank=True)
    # What the treasurer actually recorded, which may differ from `amount` (the bank is right).
    accepted_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    ledger_entry = models.OneToOneField(
        "ledger.LedgerEntry", null=True, blank=True, on_delete=models.PROTECT,
        related_name="claim",
    )
    # Makes a double tap on "I've paid" safe: the same key returns the same claim.
    idempotency_key = models.CharField(max_length=64, null=True, blank=True)  # noqa: DJ001
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TenantQuerySet.as_manager()

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="claim_amount_positive"),
            models.CheckConstraint(
                condition=Q(status__in=["pending", "accepted", "rejected", "withdrawn"]),
                name="claim_status_valid",
            ),
            models.CheckConstraint(
                condition=Q(method__in=["upi", "bank", "cash", "cheque", "other"]),
                name="claim_method_valid",
            ),
            models.CheckConstraint(
                condition=~Q(status="pending")
                | Q(resolved_by__isnull=True, ledger_entry__isnull=True),
                name="claim_pending_is_unresolved",
            ),
            models.CheckConstraint(
                condition=~Q(status="accepted")
                | Q(ledger_entry__isnull=False, accepted_amount__isnull=False,
                    resolved_by__isnull=False),
                name="claim_accepted_has_its_payment",
            ),
            models.CheckConstraint(
                condition=~Q(status="rejected") | ~Q(resolution_note=""),
                name="claim_rejected_has_a_reason",
            ),
            models.UniqueConstraint(
                fields=["society", "idempotency_key"],
                condition=Q(idempotency_key__isnull=False),
                name="claim_idempotency_key_unique_per_society",
            ),
        ]
        indexes = [
            models.Index(fields=["society", "status"]),
            models.Index(fields=["flat", "status"]),
        ]

    def __str__(self):
        return f"claim {self.pk} {self.status}"
