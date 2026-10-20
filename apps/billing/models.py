from django.db import models
from django.db.models import Q

from apps.core.tenancy import TenantQuerySet


class BillingRun(models.Model):
    """Proof that society S was billed for month P. At most one row per (society, period).

    The row is created in the SAME transaction as that month's charges, so its existence means
    "the whole month was billed" and its absence means "nothing was". The unique constraint is
    what makes the monthly job safe to run twice, concurrently, or after a crash.
    """

    society = models.ForeignKey(
        "societies.Society", on_delete=models.PROTECT, related_name="billing_runs"
    )
    period = models.DateField(help_text="First day of the billed month.")
    flats_charged = models.PositiveIntegerField(default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TenantQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["society", "period"], name="billing_run_once_per_period"
            ),
            models.CheckConstraint(
                condition=Q(period__day=1), name="billing_period_is_first_of_month"
            ),
        ]

    def __str__(self):
        return f"{self.society_id} {self.period:%Y-%m}"
