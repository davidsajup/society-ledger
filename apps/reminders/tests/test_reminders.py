"""Dues reminders: one email per person per flat that owes, at most once a week.

What these tests prove
* Only flats that owe are emailed, and each message mentions only that flat.
* Nobody is emailed twice in a week, even when two office-bearers press the button at the same
  instant (the society row lock) or the button is pressed again straight away (the cooldown).
* A failed send is recorded and retried, and one bad recipient does not stop the others.
* No email address is ever returned by the API, written to the audit log or stored in the
  reminder rows. Treasurers can send reminders without ever seeing contact details.
* Another society's flats and residents are untouchable.
"""

import time
from datetime import timedelta
from decimal import Decimal
from smtplib import SMTPException

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.core.mail import EmailMessage
from django.db import IntegrityError, transaction
from django.urls import reverse
from rest_framework.test import APIClient

from apps.audit.models import AuditLog
from apps.ledger.services import record_charge, record_payment
from apps.ledger.tests.helpers import run_in_parallel
from apps.reminders import services
from apps.reminders.models import DuesReminder, ReminderBatch
from apps.reminders.services import inr, prepare_batch, send_dues_reminders
from apps.societies.models import Flat, Society
from apps.societies.services import add_member

pytestmark = pytest.mark.django_db
D = Decimal

ADDRESSES = {"a1@example.com", "a2@example.com", "b@example.com", "shared@example.com"}


@pytest.fixture(autouse=True)
def fresh_throttle():
    cache.clear()  # the throttle counts per user in the cache, which tests share


@pytest.fixture
def world():
    """Five flats, all billed 4500. A-104 has paid in full.

    Emailable: A-101 (two addresses), A-102 (one), A-105 (two people, ONE shared address).
    A-103 owes but nobody there has an email on file. A-104 owes nothing.
    """
    society = Society.objects.create(name="Green Park", slug="green-park")
    flats = {
        label: Flat.objects.create(society=society, label=label)
        for label in ("A-101", "A-102", "A-103", "A-104", "A-105")
    }
    for flat in flats.values():
        record_charge(society=society, flat=flat, amount=D("4500.00"))

    people = {}

    def member(username, role, flat=None, email="", first_name=""):
        user = get_user_model().objects.create_user(
            username=username, password="x", first_name=first_name
        )
        membership = add_member(society=society, user=user, role=role, flat=flat)
        membership.email = email
        membership.save(update_fields=["email"])
        client = APIClient()
        client.force_authenticate(user=user)
        people[username] = (user, client)

    member("treasurer", "treasurer")
    member("president", "president")
    member("secretary", "secretary")
    member("res_a1", "resident", flats["A-101"], "a1@example.com", "Asha")
    member("res_a2", "resident", flats["A-101"], "a2@example.com")
    member("res_b", "resident", flats["A-102"], "b@example.com")
    member("res_c", "resident", flats["A-103"])
    member("res_d", "resident", flats["A-104"], "d@example.com")
    member("res_e1", "resident", flats["A-105"], "shared@example.com")
    member("res_e2", "resident", flats["A-105"], "SHARED@example.com")
    record_payment(
        society=society, flat=flats["A-104"], amount=D("4500.00"), actor=people["treasurer"][0]
    )
    return {"society": society, "flats": flats, "people": people}


def client(world, name):
    return world["people"][name][1]


def user(world, name):
    return world["people"][name][0]


def url(world, route):
    return reverse(route, kwargs={"society_id": world["society"].id})


def press(world, who="treasurer"):
    return client(world, who).post(url(world, "reminder-send"), {}, format="json")


def sent_to():
    return sorted(message.to[0] for message in mail.outbox)


# --- Who gets an email ------------------------------------------------------------------------


def test_only_flats_that_owe_and_have_an_email_are_emailed(world):
    response = press(world)

    assert response.status_code == 200
    assert {m.to[0].lower() for m in mail.outbox} == ADDRESSES
    assert len(mail.outbox) == 4  # two for A-101, one for A-102, ONE for the shared A-105 address
    body = response.json()
    assert (body["flats_owing"], body["flats_reminded"], body["flats_without_email"]) == (4, 3, 1)
    assert (body["sent"], body["failed"]) == (4, 0)


def test_a_paid_up_flat_is_never_emailed(world):
    press(world)

    assert "d@example.com" not in sent_to()


def test_each_email_mentions_only_its_own_flat_and_amount(world):
    record_charge(society=world["society"], flat=world["flats"]["A-102"], amount=D("1250.50"))

    press(world)

    message = next(m for m in mail.outbox if m.to == ["b@example.com"])
    assert "Flat A-102" in message.subject and "Green Park" in message.subject
    assert "5,750.50" in message.body  # 4500 + 1250.50, in Indian digit grouping
    assert "Hello Resident" in message.body  # no first name on file
    for other in ("A-101", "A-103", "A-104", "A-105", "4,500.00"):
        assert other not in message.body
    greeting = next(m for m in mail.outbox if m.to == ["a1@example.com"])
    assert "Hello Asha" in greeting.body


def test_nothing_to_do_creates_no_batch_and_sends_nothing(world):
    for label in ("A-101", "A-102", "A-103", "A-105"):
        record_payment(
            society=world["society"], flat=world["flats"][label], amount=D("4500.00"),
            actor=user(world, "treasurer"),
        )

    response = press(world)

    assert response.status_code == 200
    assert response.json()["flats_reminded"] == 0
    assert (ReminderBatch.objects.count(), len(mail.outbox)) == (0, 0)


def test_another_societys_flats_and_residents_are_never_touched(world):
    other = Society.objects.create(name="Lake View", slug="lake-view")
    their_flat = Flat.objects.create(society=other, label="B-1")
    record_charge(society=other, flat=their_flat, amount=D("999.00"))
    stranger = get_user_model().objects.create_user(username="stranger", password="x")
    membership = add_member(society=other, user=stranger, role="resident", flat=their_flat)
    membership.email = "stranger@example.com"
    membership.save(update_fields=["email"])

    press(world)

    assert "stranger@example.com" not in sent_to()
    assert DuesReminder.objects.filter(society=other).count() == 0


# --- Nothing secret leaks ---------------------------------------------------------------------


def test_the_preview_and_the_result_contain_counts_and_no_addresses(world):
    preview = client(world, "treasurer").get(url(world, "reminder-preview"))
    result = press(world)

    assert preview.json() == {
        "flats_owing": 4, "flats_cooling_down": 0, "flats_without_email": 1,
        "flats_eligible": 3, "recipients": 4, "batch_limit": 100,
    }
    assert "@" not in preview.content.decode() + result.content.decode()


def test_no_address_is_stored_in_the_reminder_rows_or_the_audit_log(world):
    press(world)

    for row in DuesReminder.objects.values():
        assert "@" not in " ".join(str(v) for v in row.values())
    audit = AuditLog.objects.get(action="reminders.sent")
    assert audit.data == {"flats": 3, "recipients": 4}
    assert audit.actor == user(world, "treasurer")


def test_the_rows_record_what_was_owed_and_that_it_was_sent(world):
    press(world)

    rows = DuesReminder.objects.all()
    assert rows.count() == 4
    assert {r.status for r in rows} == {"sent"}
    assert all(r.sent_at is not None and r.amount_owed == D("4500.00") for r in rows)


# --- No nagging -------------------------------------------------------------------------------


def test_pressing_again_straight_away_sends_nothing_more(world):
    press(world)
    mail.outbox.clear()

    again = press(world)

    assert len(mail.outbox) == 0
    assert again.json()["flats_cooling_down"] == 3
    assert again.json()["flats_reminded"] == 0


def test_a_flat_is_reminded_again_only_after_the_cooldown(world, monkeypatch):
    press(world)
    mail.outbox.clear()
    real_now = services.timezone.now

    monkeypatch.setattr(services.timezone, "now", lambda: real_now() + timedelta(days=6))
    press(world)
    assert len(mail.outbox) == 0  # still inside the week

    monkeypatch.setattr(services.timezone, "now", lambda: real_now() + timedelta(days=8))
    press(world)
    assert len(mail.outbox) == 4  # the week is over


# --- Failures are recorded and retried ----------------------------------------------------------


def break_one_address(monkeypatch, address):
    real_send = EmailMessage.send

    def send(self, fail_silently=False):
        if self.to == [address]:
            raise SMTPException("mailbox full")
        return real_send(self, fail_silently=fail_silently)

    monkeypatch.setattr(EmailMessage, "send", send)
    return real_send


def test_one_failing_recipient_is_recorded_and_the_others_still_get_theirs(world, monkeypatch):
    break_one_address(monkeypatch, "b@example.com")

    result = press(world).json()

    assert (result["sent"], result["failed"]) == (3, 1)
    failed = DuesReminder.objects.get(status="failed")
    assert failed.failure == "SMTPException"  # the kind of error, not the message
    assert "mailbox" not in failed.failure and "@" not in failed.failure
    assert "b@example.com" not in sent_to()


def test_pressing_again_retries_only_what_failed(world, monkeypatch):
    real_send = break_one_address(monkeypatch, "b@example.com")
    press(world)
    mail.outbox.clear()
    monkeypatch.setattr(EmailMessage, "send", real_send)  # the problem is fixed

    retry = press(world).json()

    assert sent_to() == ["b@example.com"]
    assert (retry["sent"], retry["failed"]) == (1, 0)


def test_a_send_that_died_midway_does_not_silence_a_flat_for_a_week(world, monkeypatch):
    """prepare_batch committed its pending rows, then the process died before sending."""
    prepare_batch(society=world["society"], actor=user(world, "treasurer"))
    assert len(mail.outbox) == 0 and DuesReminder.objects.filter(status="pending").count() == 4
    real_now = services.timezone.now

    # Within the grace period a pending row still counts: a send may be in progress.
    press(world)
    assert len(mail.outbox) == 0

    monkeypatch.setattr(services.timezone, "now", lambda: real_now() + timedelta(minutes=20))
    press(world)
    assert len(mail.outbox) == 4


# --- The cap ----------------------------------------------------------------------------------


def test_at_most_the_cap_is_sent_per_press_and_the_next_press_finishes_the_job(world, monkeypatch):
    monkeypatch.setattr(services, "MAX_PER_PRESS", 3)

    first = press(world).json()
    second = press(world).json()
    third = press(world).json()

    # A-101 has two addresses; A-102 adds one (3 total); A-105 would be a fourth.
    assert (first["flats_reminded"], first["flats_deferred"], first["sent"]) == (2, 1, 3)
    assert (second["flats_reminded"], second["flats_deferred"], second["sent"]) == (1, 0, 1)
    assert third["sent"] == 0
    assert sorted(m.to[0].lower() for m in mail.outbox) == sorted(ADDRESSES)  # each exactly once


# --- Two presses at once ----------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_two_office_bearers_pressing_at_once_email_each_person_exactly_once(world, monkeypatch):
    """Proves: prepare_batch locks the society row. The second press waits, then sees the first
    one's rows in the cooldown check and finds nothing left to do.

    Without the lock both read the same plan, both write rows and both send: every resident
    gets two emails.
    """
    real_plan = services.make_plan

    def slow(society):  # widen the window between planning and writing the rows
        plan = real_plan(society)
        time.sleep(0.2)
        return plan

    monkeypatch.setattr(services, "make_plan", slow)
    actors = [user(world, "treasurer"), user(world, "president")]

    run_in_parallel(
        2, lambda i: send_dues_reminders(society=world["society"], actor=actors[i])
    )

    assert len(mail.outbox) == 4
    assert sorted(m.to[0].lower() for m in mail.outbox) == sorted(ADDRESSES)
    assert DuesReminder.objects.count() == 4


# --- Atomicity --------------------------------------------------------------------------------


def test_if_the_audit_write_fails_nothing_is_recorded_and_nothing_is_sent(world, monkeypatch):
    def boom(**kwargs):
        raise RuntimeError("audit down")

    monkeypatch.setattr(services.audit, "record", boom)

    with pytest.raises(RuntimeError):
        press(world)

    assert (ReminderBatch.objects.count(), DuesReminder.objects.count()) == (0, 0)
    assert len(mail.outbox) == 0


# --- Permissions ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "who, allowed",
    [("treasurer", True), ("president", True), ("secretary", True), ("res_a1", False)],
)
def test_who_may_preview_and_send(world, who, allowed):
    preview = client(world, who).get(url(world, "reminder-preview"))
    send = press(world, who)

    assert (preview.status_code == 200) is allowed
    assert (send.status_code == 200) is allowed
    assert (len(mail.outbox) > 0) is allowed
    if not allowed:
        assert (preview.status_code, send.status_code) == (403, 403)


def test_the_button_can_be_pressed_six_times_an_hour_and_no_more(world):
    codes = [press(world).status_code for _ in range(7)]

    assert codes == [200] * 6 + [429]


# --- The database's own rules -----------------------------------------------------------------


def _batch(world):
    return ReminderBatch.objects.create(
        society=world["society"], created_by=user(world, "treasurer"), flats_owing=1,
        flats_cooling_down=0, flats_without_email=0, flats_deferred=0, flats_reminded=1,
        recipients=1,
    )


def _row(world, batch, **fields):
    values = {
        "society": world["society"], "batch": batch, "flat": world["flats"]["A-101"],
        "recipient": user(world, "res_a1").memberships.get(), "amount_owed": D("10.00"),
    }
    return DuesReminder(**{**values, **fields})


@pytest.mark.parametrize(
    "fields",
    [{"amount_owed": D("0")}, {"status": "sent"}, {"status": "lost"}],
)
def test_the_database_refuses_an_impossible_reminder_row(world, fields):
    row = _row(world, _batch(world), **fields)

    with pytest.raises(IntegrityError), transaction.atomic():
        row.save()


def test_a_person_gets_one_row_per_batch(world):
    batch = _batch(world)
    _row(world, batch).save()

    with pytest.raises(IntegrityError), transaction.atomic():
        _row(world, batch).save()


# --- The money format ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "amount, expected",
    [
        ("0", "0.00"), ("999.5", "999.50"), ("1000", "1,000.00"), ("4500", "4,500.00"),
        ("99999.99", "99,999.99"), ("123456.7", "1,23,456.70"), ("10000000", "1,00,00,000.00"),
    ],
)
def test_amounts_use_indian_digit_grouping(amount, expected):
    assert inr(D(amount)) == expected
