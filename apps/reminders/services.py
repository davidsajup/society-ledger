from datetime import timedelta
from decimal import Decimal

from django.core.mail import EmailMessage, get_connection
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.audit import services as audit
from apps.audit.models import AuditLog
from apps.reports.selectors import society_summary
from apps.societies.models import Membership, Society

from .models import DuesReminder, ReminderBatch

# A flat is reminded at most once in this long. Nagging teaches people to ignore the emails.
COOLDOWN = timedelta(days=7)
# A "pending" row older than this is a send that died (a crash, a restart). It stops counting as
# "already reminded", so the next press retries it instead of leaving the flat silent for a week.
PENDING_GRACE = timedelta(minutes=15)
# Emails per press. The request stays short and no background worker is needed: if more are due
# the result says so, and the cooldown makes the next press pick up exactly the rest.
MAX_PER_PRESS = 100


def inr(amount: Decimal) -> str:
    """4500 -> '4,500.00'; 123456.7 -> '1,23,456.70' (Indian digit grouping)."""
    whole, _, fraction = f"{amount:.2f}".partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join([*groups, tail])
    return f"{whole}.{fraction}"


class Plan:
    """Who would be emailed right now, and why everyone else would not."""

    def __init__(self, owing, cooling_ids, recipients_by_flat):
        self.flats_owing = len(owing)
        self.cooling = [f for f in owing if f["id"] in cooling_ids]
        rest = [f for f in owing if f["id"] not in cooling_ids]
        self.without_email = [f for f in rest if not recipients_by_flat.get(f["id"])]
        self.eligible = [
            (f, recipients_by_flat[f["id"]]) for f in rest if recipients_by_flat.get(f["id"])
        ]

    def summary(self):
        return {
            "flats_owing": self.flats_owing,
            "flats_cooling_down": len(self.cooling),
            "flats_without_email": len(self.without_email),
            "flats_eligible": len(self.eligible),
            "recipients": sum(len(members) for _flat, members in self.eligible),
        }


def _cooling_flat_ids(society, now):
    recent = Q(status=DuesReminder.Status.SENT, created_at__gte=now - COOLDOWN) | Q(
        status=DuesReminder.Status.PENDING, created_at__gte=now - PENDING_GRACE
    )
    return set(
        DuesReminder.objects.for_society(society).filter(recent).values_list("flat_id", flat=True)
    )


def make_plan(society) -> Plan:
    owing = [f for f in society_summary(society)["flats"] if f["outstanding"] > 0]
    ids = [f["id"] for f in owing]

    recipients = {}
    people = (
        Membership.objects.for_society(society)
        .filter(flat_id__in=ids)
        .exclude(email="")
        .select_related("user")
        .order_by("flat_id", "id")
    )
    seen = set()
    for member in people:
        # Two people sharing one address get one email, not two.
        key = (member.flat_id, member.email.lower())
        if key in seen:
            continue
        seen.add(key)
        recipients.setdefault(member.flat_id, []).append(member)

    return Plan(owing, _cooling_flat_ids(society, timezone.now()), recipients)


def preview(society) -> dict:
    """Counts only. Never an address."""
    return {**make_plan(society).summary(), "batch_limit": MAX_PER_PRESS}


@transaction.atomic
def prepare_batch(*, society, actor):
    """Decide who gets an email and write one pending row per person. Sends nothing.

    The society row is locked first. Two office-bearers pressing the button at the same instant
    then queue here, and the second one sees the first one's rows in the cooldown check and
    finds nothing left to do, so no flat is emailed twice.

    Returns (batch, plan); batch is None when there is nobody to email.
    """
    Society.objects.select_for_update().get(pk=society.pk)
    plan = make_plan(society)

    chosen, recipients = [], 0
    for flat, members in plan.eligible:
        if chosen and recipients + len(members) > MAX_PER_PRESS:
            break
        chosen.append((flat, members))
        recipients += len(members)
    if not chosen:
        return None, plan

    batch = ReminderBatch.objects.create(
        society=society,
        created_by=actor,
        flats_owing=plan.flats_owing,
        flats_cooling_down=len(plan.cooling),
        flats_without_email=len(plan.without_email),
        flats_deferred=len(plan.eligible) - len(chosen),
        flats_reminded=len(chosen),
        recipients=recipients,
    )
    DuesReminder.objects.bulk_create(
        [
            DuesReminder(
                society=society,
                batch=batch,
                flat_id=flat["id"],
                recipient=member,
                amount_owed=flat["outstanding"],
            )
            for flat, members in chosen
            for member in members
        ]
    )
    # Counts only: an audit row must never hold anybody's contact details.
    audit.record(
        society=society,
        actor=actor,
        action=AuditLog.Action.REMINDERS_SENT,
        object_type="reminder_batch",
        object_id=batch.pk,
        data={"flats": len(chosen), "recipients": recipients},
    )
    return batch, plan


def build_message(reminder, connection=None) -> EmailMessage:
    """The email for one pending reminder. It mentions this flat and nothing else."""
    society = reminder.society
    flat = reminder.flat
    member = reminder.recipient
    name = member.user.first_name or "Resident"
    body = (
        f"Hello {name},\n\n"
        f"This is a reminder from {society.name}. Flat {flat.label} currently owes "
        f"Rs {inr(reminder.amount_owed)} in maintenance.\n\n"
        "If you have already paid, please open the app and tap \"I have paid\", or tell "
        "the treasurer, so the payment can be recorded.\n\n"
        f"Thank you,\n{society.name}\n"
    )
    return EmailMessage(
        subject=f"Maintenance reminder: Flat {flat.label}, {society.name}",
        body=body,
        to=[member.email],
        connection=connection,
    )


def deliver_batch(batch) -> dict:
    """Send every pending email in `batch` and record what happened. Never raises for a bad send.

    This runs AFTER prepare_batch has committed, deliberately outside any transaction: a
    network call must not hold a database lock, and an email that has gone out cannot be rolled
    back. One failing recipient does not stop the others.
    """
    rows = (
        DuesReminder.objects.filter(batch=batch, status=DuesReminder.Status.PENDING)
        .select_related("society", "flat", "recipient__user")
        .order_by("id")
    )
    sent = failed = 0
    connection = get_connection()  # one connection for the whole batch
    for row in rows:
        try:
            build_message(row, connection).send(fail_silently=False)
        except Exception as exc:  # noqa: BLE001 - any failure is recorded, never lost
            row.status = DuesReminder.Status.FAILED
            row.failure = type(exc).__name__[:80]
            row.save(update_fields=["status", "failure"])
            failed += 1
        else:
            row.status = DuesReminder.Status.SENT
            row.sent_at = timezone.now()
            row.save(update_fields=["status", "sent_at"])
            sent += 1
    return {"sent": sent, "failed": failed}


def send_dues_reminders(*, society, actor) -> dict:
    """The whole button: decide, record, send. Returns counts only."""
    batch, plan = prepare_batch(society=society, actor=actor)
    summary = plan.summary()
    if batch is None:
        return {**summary, "flats_reminded": 0, "flats_deferred": 0, "sent": 0, "failed": 0}
    outcome = deliver_batch(batch)
    return {
        **summary,
        "flats_reminded": batch.flats_reminded,
        "flats_deferred": batch.flats_deferred,
        **outcome,
    }
