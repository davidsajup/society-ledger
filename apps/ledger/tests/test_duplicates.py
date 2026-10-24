"""The duplicate warning: the same amount on the same flat moments ago needs a deliberate yes.

The idempotency key stops a retry of one request. It cannot stop a person who closes the form
and starts over (new form, new key). These tests pin down what the warning does and, as
important, what it leaves alone.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from apps.audit.models import AuditLog
from apps.ledger import services
from apps.ledger.models import LedgerEntry
from apps.ledger.selectors import outstanding_for_flat
from apps.ledger.services import (
    PaymentExceedsOutstanding,
    PossibleDuplicatePayment,
    record_charge,
    record_payment,
    reverse_entry,
)
from apps.ledger.tests.helpers import build_world, run_in_parallel
from apps.societies.models import Flat, Society
from apps.societies.services import add_member

D = Decimal

pytestmark = pytest.mark.django_db


def payments(flat):
    return LedgerEntry.objects.filter(flat=flat, kind="payment")


def pay(society, flat, treasurer, amount="30.00", **kwargs):
    return record_payment(
        society=society, flat=flat, amount=D(amount), actor=treasurer, **kwargs
    )


# --- The warning ----------------------------------------------------------------------------


def test_the_same_amount_again_is_refused_until_confirmed_and_writes_nothing():
    society, flat, treasurer = build_world("100.00")
    first, _ = pay(society, flat, treasurer)
    audit_rows = AuditLog.objects.count()

    with pytest.raises(PossibleDuplicatePayment) as exc:
        pay(society, flat, treasurer)

    assert exc.value.previous == first
    assert payments(flat).count() == 1
    assert AuditLog.objects.count() == audit_rows
    assert outstanding_for_flat(flat) == D("70.00")


def test_confirming_records_it_and_the_audit_row_says_it_was_confirmed():
    society, flat, treasurer = build_world("100.00")
    first, _ = pay(society, flat, treasurer)

    second, created = pay(society, flat, treasurer, confirm_duplicate=True)

    assert created is True
    assert payments(flat).count() == 2
    audit = AuditLog.objects.filter(object_id=second.pk, action="payment.recorded").get()
    assert audit.data["confirmed_duplicate_of"] == first.pk


def test_an_ordinary_payment_has_no_duplicate_mark_in_its_audit_row():
    society, flat, treasurer = build_world("100.00")
    entry, _ = pay(society, flat, treasurer)

    audit = AuditLog.objects.filter(object_id=entry.pk, action="payment.recorded").get()
    assert "confirmed_duplicate_of" not in audit.data


def test_a_different_amount_is_not_questioned():
    society, flat, treasurer = build_world("100.00")
    pay(society, flat, treasurer, "30.00")

    pay(society, flat, treasurer, "30.01")

    assert payments(flat).count() == 2


def test_the_same_amount_on_another_flat_is_not_questioned():
    society, flat, treasurer = build_world("100.00")
    other = Flat.objects.create(society=society, label="A-102")
    record_charge(society=society, flat=other, amount=D("100.00"))
    pay(society, flat, treasurer)

    pay(society, other, treasurer)

    assert payments(other).count() == 1


def test_the_same_amount_in_another_society_is_not_questioned():
    society, flat, treasurer = build_world("100.00")
    elsewhere = Society.objects.create(name="Blue Park", slug="blue-park")
    their_flat = Flat.objects.create(society=elsewhere, label="A-101")
    record_charge(society=elsewhere, flat=their_flat, amount=D("100.00"))
    their_treasurer = get_user_model().objects.create_user(username="other", password="x")
    pay(society, flat, treasurer)

    pay(elsewhere, their_flat, their_treasurer)

    assert payments(their_flat).count() == 1


def test_someone_else_recording_the_same_amount_is_also_warned():
    # Two office-bearers both entering the same cash receipt is just as likely a duplicate.
    society, flat, treasurer = build_world("100.00")
    colleague = get_user_model().objects.create_user(username="colleague", password="x")
    pay(society, flat, treasurer)

    with pytest.raises(PossibleDuplicatePayment):
        pay(society, flat, colleague)


def test_a_payment_older_than_the_window_is_not_questioned(monkeypatch):
    society, flat, treasurer = build_world("100.00")
    pay(society, flat, treasurer)
    real_now = services.timezone.now
    later = services.DUPLICATE_WINDOW + timedelta(minutes=1)
    monkeypatch.setattr(services.timezone, "now", lambda: real_now() + later)

    pay(society, flat, treasurer)

    assert payments(flat).count() == 2


def test_a_payment_just_inside_the_window_still_counts(monkeypatch):
    society, flat, treasurer = build_world("100.00")
    pay(society, flat, treasurer)
    real_now = services.timezone.now
    almost = services.DUPLICATE_WINDOW - timedelta(minutes=1)
    monkeypatch.setattr(services.timezone, "now", lambda: real_now() + almost)

    with pytest.raises(PossibleDuplicatePayment):
        pay(society, flat, treasurer)


# --- What the warning must leave alone ------------------------------------------------------


def test_a_reversed_payment_no_longer_counts():
    # Mistake noticed and corrected: recording the right payment must not be questioned.
    society, flat, treasurer = build_world("100.00")
    wrong, _ = pay(society, flat, treasurer)
    reverse_entry(society=society, entry=wrong, actor=treasurer)

    pay(society, flat, treasurer)

    assert payments(flat).count() == 2


def test_a_reversal_entry_is_not_mistaken_for_a_payment():
    # Reversing a charge appends a payment-kind entry. It is a correction, not money received.
    society, flat, treasurer = build_world("100.00")
    second_charge = record_charge(society=society, flat=flat, amount=D("100.00"))
    reverse_entry(society=society, entry=second_charge, actor=treasurer)

    entry, created = pay(society, flat, treasurer, "100.00")

    assert created is True
    assert entry.reverses_id is None


def test_a_retry_with_the_same_key_gets_the_original_back_not_a_warning():
    society, flat, treasurer = build_world("100.00")
    first, _ = pay(society, flat, treasurer, idempotency_key="k1")

    again, created = pay(society, flat, treasurer, idempotency_key="k1")

    assert (again, created) == (first, False)


def test_overpayment_wins_over_the_warning():
    society, flat, treasurer = build_world("30.00")
    pay(society, flat, treasurer)  # the flat now owes nothing

    with pytest.raises(PaymentExceedsOutstanding):
        pay(society, flat, treasurer)


# --- Concurrency ----------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_two_simultaneous_identical_submissions_record_exactly_one(widen_race_window):
    """Two tabs submit the same amount at the same instant, each with its own key.

    Proves: the duplicate lookup runs after the flat lock. The loser queues, then sees the
    winner's committed payment and is warned. Look it up before the lock and both pass.
    """
    society, flat, treasurer = build_world("100.00")

    def submit(i):
        try:
            pay(society, flat, treasurer, idempotency_key=f"tab-{i}")
            return "recorded"
        except PossibleDuplicatePayment:
            return "warned"

    results = run_in_parallel(2, submit)

    assert sorted(results) == ["recorded", "warned"]
    assert payments(flat).count() == 1


# --- Over HTTP ------------------------------------------------------------------------------


@pytest.fixture
def api():
    society = Society.objects.create(name="Green Park", slug="green-park")
    flat = Flat.objects.create(society=society, label="A-101")
    record_charge(society=society, flat=flat, amount=D("100.00"))
    treasurer = get_user_model().objects.create_user(username="treasurer", password="x")
    add_member(society=society, user=treasurer, role="treasurer", flat=None)
    client = APIClient()
    client.force_authenticate(user=treasurer)
    url = reverse("payment-create", kwargs={"society_id": society.id, "flat_id": flat.id})
    return client, url, flat


def test_http_second_identical_payment_is_409_with_a_code_and_the_earlier_payment(api):
    client, url, flat = api
    assert client.post(url, {"amount": "30.00"}, format="json").status_code == 201

    response = client.post(url, {"amount": "30.00"}, format="json")

    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "possible_duplicate"
    assert body["previous"]["amount"] == "30.00"
    assert body["previous"]["created_at"]
    assert payments(flat).count() == 1


def test_http_confirm_duplicate_true_records_it(api):
    client, url, flat = api
    client.post(url, {"amount": "30.00"}, format="json")

    response = client.post(url, {"amount": "30.00", "confirm_duplicate": True}, format="json")

    assert response.status_code == 201
    assert payments(flat).count() == 2


def test_http_the_same_key_after_a_warning_still_works_because_nothing_was_stored(api):
    client, url, flat = api
    client.post(url, {"amount": "30.00"}, format="json")

    first = client.post(
        url, {"amount": "30.00"}, format="json", headers={"Idempotency-Key": "k2"}
    )
    confirmed = client.post(
        url,
        {"amount": "30.00", "confirm_duplicate": True},
        format="json",
        headers={"Idempotency-Key": "k2"},
    )

    assert first.status_code == 409
    assert confirmed.status_code == 201
    assert payments(flat).count() == 2


def test_http_a_key_clash_has_its_own_code_so_the_browser_can_tell_them_apart(api):
    client, url, _ = api
    client.post(url, {"amount": "30.00"}, format="json", headers={"Idempotency-Key": "k3"})

    response = client.post(
        url, {"amount": "40.00"}, format="json", headers={"Idempotency-Key": "k3"}
    )

    assert response.status_code == 409
    assert response.json()["code"] == "idempotency_key_reused"


def test_http_confirm_duplicate_must_be_a_real_boolean(api):
    client, url, flat = api

    response = client.post(
        url, {"amount": "30.00", "confirm_duplicate": "maybe"}, format="json"
    )

    assert response.status_code == 400
    assert payments(flat).count() == 0
