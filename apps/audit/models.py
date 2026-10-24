from django.conf import settings
from django.db import models

from apps.core.append_only import AppendOnlyModel, AppendOnlyQuerySet


class AuditLog(AppendOnlyModel):
    """Who did what to the money, and when. Append-only, written inside the money transaction.

    The target is stored as a plain (object_type, object_id) pair instead of a foreign key, so
    this app depends on nothing and an audit row can never block or cascade anything.
    """

    class Action(models.TextChoices):
        PAYMENT_RECORDED = "payment.recorded"
        ENTRY_REVERSED = "entry.reversed"
        BILLING_RUN = "billing.run"
        EXPENSE_RECORDED = "expense.recorded"
        EXPENSE_REVERSED = "expense.reversed"
        MEMBER_CREATED = "member.created"
        CREDENTIALS_REISSUED = "credentials.reissued"
        MEMBER_UPDATED = "member.updated"
        SOCIETY_CREATED = "society.created"
        SOCIETY_IMPORTED = "society.imported"

    society = models.ForeignKey(
        "societies.Society", on_delete=models.PROTECT, related_name="audit_logs"
    )
    # Null for system jobs (the billing task).
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    action = models.CharField(max_length=40, choices=Action.choices)
    flat = models.ForeignKey(
        "societies.Flat", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    object_type = models.CharField(max_length=40)
    object_id = models.PositiveBigIntegerField()
    amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    # Small extra context. Money inside it must be a string: Decimal is not JSON.
    data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = AppendOnlyQuerySet.as_manager()

    class Meta:
        indexes = [models.Index(fields=["society", "-created_at"])]

    def __str__(self):
        return f"{self.action} {self.object_type}#{self.object_id}"
