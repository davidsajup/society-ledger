from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.append_only import AppendOnlyModel, AppendOnlyQuerySet


class Expense(AppendOnlyModel):
    """Money the society spent. Append-only, like the ledger.

    A mistake is fixed by appending a reversing expense (`reverses` -> the original). Reversals
    count as negative spending in totals. Protected in Python and by a Postgres trigger.
    """

    class Category(models.TextChoices):
        UTILITIES = "utilities"
        REPAIRS = "repairs"
        SALARIES = "salaries"
        SECURITY = "security"
        OTHER = "other"

    society = models.ForeignKey(
        "societies.Society", on_delete=models.PROTECT, related_name="expenses"
    )
    category = models.CharField(max_length=20, choices=Category.choices)
    description = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    paid_on = models.DateField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    # NULL, not '': the unique constraint ignores NULLs, but '' would collide with itself.
    idempotency_key = models.CharField(max_length=64, null=True, blank=True)  # noqa: DJ001
    reverses = models.OneToOneField(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="reversed_by"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = AppendOnlyQuerySet.as_manager()

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="expense_amount_positive"),
            models.UniqueConstraint(
                fields=["society", "idempotency_key"],
                condition=Q(idempotency_key__isnull=False),
                name="expense_idempotency_key_unique_per_society",
            ),
        ]
        indexes = [models.Index(fields=["society", "-paid_on"])]

    def __str__(self):
        return f"{self.category} {self.amount} ({self.society_id})"
