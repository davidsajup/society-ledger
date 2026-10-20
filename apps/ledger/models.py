from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.append_only import AppendOnlyError, AppendOnlyModel, AppendOnlyQuerySet

__all__ = ["AppendOnlyError", "LedgerEntry"]  # AppendOnlyError re-exported for older imports


class LedgerEntry(AppendOnlyModel):
    """One immutable money movement for one flat.

    Amounts are always positive; `kind` gives the direction:
      charge  -> the flat owes more
      payment -> the flat owes less
    A mistake is fixed by appending a reversing entry (`reverses` -> the original), never by
    editing. Append-only is enforced twice: here in Python, and by a Postgres trigger
    (migration 0002), so even raw SQL cannot rewrite history.
    """

    class Kind(models.TextChoices):
        CHARGE = "charge"
        PAYMENT = "payment"

    society = models.ForeignKey(
        "societies.Society", on_delete=models.PROTECT, related_name="ledger_entries"
    )
    flat = models.ForeignKey(
        "societies.Flat", on_delete=models.PROTECT, related_name="ledger_entries"
    )
    kind = models.CharField(max_length=10, choices=Kind.choices)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    # Null for entries created by the system (the billing job in M3).
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    note = models.CharField(max_length=200, blank=True)
    # Client-supplied key that makes a retried request safe (see record_payment).
    # NULL, not '': the unique constraint ignores NULLs, but '' would collide with itself.
    idempotency_key = models.CharField(max_length=64, null=True, blank=True)  # noqa: DJ001
    # OneToOne: an entry can be reversed at most once.
    reverses = models.OneToOneField(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="reversed_by"
    )
    # Set only on charges created by the monthly billing job.
    billing_run = models.ForeignKey(
        "billing.BillingRun",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="charges",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = AppendOnlyQuerySet.as_manager()

    class Meta:
        verbose_name_plural = "ledger entries"
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="ledger_amount_positive"),
            models.CheckConstraint(
                condition=Q(kind__in=["charge", "payment"]), name="ledger_kind_valid"
            ),
            # The same key may be reused by a different society, and many entries may have no key.
            models.UniqueConstraint(
                fields=["society", "idempotency_key"],
                condition=Q(idempotency_key__isnull=False),
                name="ledger_idempotency_key_unique_per_society",
            ),
            # Second, independent guard behind BillingRun's own unique constraint: a flat gets
            # at most one charge per billing run, even if the run-level check had a bug.
            models.UniqueConstraint(
                fields=["flat", "billing_run"],
                condition=Q(billing_run__isnull=False),
                name="ledger_one_charge_per_flat_per_billing_run",
            ),
        ]
        indexes = [models.Index(fields=["flat", "kind"])]

    def __str__(self):
        return f"{self.kind} {self.amount} flat={self.flat_id}"
