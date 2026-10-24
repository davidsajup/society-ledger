from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.tenancy import TenantQuerySet


class ReminderBatch(models.Model):
    """One press of "Remind flats that owe": who pressed it, and what it covered.

    The counts say why a flat was or was not emailed, so a treasurer who asks "why did Flat B-4
    not get one?" can be answered without exposing anybody's address.
    """

    society = models.ForeignKey(
        "societies.Society", on_delete=models.PROTECT, related_name="reminder_batches"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    flats_owing = models.PositiveIntegerField()
    flats_cooling_down = models.PositiveIntegerField()
    flats_without_email = models.PositiveIntegerField()
    # Flats that were eligible but left for the next press (the batch cap).
    flats_deferred = models.PositiveIntegerField()
    flats_reminded = models.PositiveIntegerField()
    recipients = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TenantQuerySet.as_manager()

    def __str__(self):
        return f"reminder batch {self.pk}"


class DuesReminder(models.Model):
    """One email to one person about one flat's dues. Written BEFORE the email is sent.

    That order is the point (an outbox): the row is committed first, the network call happens
    afterwards, and the row is then marked sent or failed. A crash in between leaves a visible
    "pending" row, never a silently lost or silently repeated email.

    No email address is stored here. The address is read from the person's Membership at send
    time, so contact details live in one place only.
    """

    class Status(models.TextChoices):
        PENDING = "pending"
        SENT = "sent"
        FAILED = "failed"

    society = models.ForeignKey(
        "societies.Society", on_delete=models.PROTECT, related_name="dues_reminders"
    )
    batch = models.ForeignKey(ReminderBatch, on_delete=models.PROTECT, related_name="reminders")
    flat = models.ForeignKey(
        "societies.Flat", on_delete=models.PROTECT, related_name="dues_reminders"
    )
    recipient = models.ForeignKey(
        "societies.Membership", on_delete=models.PROTECT, related_name="+"
    )
    # What the flat owed when the reminder was prepared.
    amount_owed = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    # The kind of failure only (an exception class name). Never an address or a message body.
    failure = models.CharField(max_length=80, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TenantQuerySet.as_manager()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["batch", "recipient"], name="reminder_once_per_batch"),
            models.CheckConstraint(condition=Q(amount_owed__gt=0), name="reminder_amount_positive"),
            models.CheckConstraint(
                condition=Q(status__in=["pending", "sent", "failed"]), name="reminder_status_valid"
            ),
            models.CheckConstraint(
                condition=~Q(status="sent") | Q(sent_at__isnull=False),
                name="reminder_sent_has_a_time",
            ),
        ]
        indexes = [models.Index(fields=["flat", "created_at"])]

    def __str__(self):
        return f"reminder {self.pk} {self.status}"
