"""Payment claims: a resident says "I paid"; an office-bearer checks and records the real payment.

What these tests prove
* A claim never changes a balance or the ledger. Only accepting it does, through record_payment.
* Only someone who lives in a flat can claim for it; everyone else gets a plain 404.
* A claim is answered exactly once, even when two office-bearers act at the same instant.
* Accepting is all or nothing: the payment, the link back to the claim and the audit rows are
  written together or not at all.
* Nobody answers a claim for the flat they live in.
* Another society's claims are invisible and untouchable.
"""

import time
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.audit.models import AuditLog
from apps.claims import services
from apps.claims.models import PaymentClaim
from apps.claims.services import (
    ClaimNotPending,
    TooManyPendingClaims,
    accept_claim,
    submit_claim,
)
from apps.ledger.models import LedgerEntry
from apps.ledger.selectors import outstanding_for_flat
from apps.ledger.services import record_charge, record_payment
from apps.ledger.tests.helpers import run_in_parallel
from apps.societies.models import Flat, Society
from apps.societies.services import add_member

pytestmark = pytest.mark.django_db
D = Decimal


def today():
    return timezone.localdate()


@pytest.fixture
def world():
    society = Society.objects.create(name="Green Park", slug="green-park")
    flats = {
        label: Flat.objects.create(society=society, label=label, maintenance_amount=D("4500"))
        for label in ("A-101", "A-102", "A-103")
    }
    for flat in flats.values():
        record_charge(society=society, flat=flat, amount=D("4500.00"))
    users = {}
    for name, role, flat in [
        ("treasurer", "treasurer", None),
        ("president", "president", None),
        ("secretary", "secretary", flats["A-103"]),  # an office-bearer who lives in a flat
        ("res_a", "resident", flats["A-101"]),
        ("res_b", "resident", flats["A-102"]),
    ]:
        user = get_user_model().objects.create_user(username=name, password="x")
        add_member(society=society, user=user, role=role, flat=flat)
        client = APIClient()
        client.force_authenticate(user=user)
        users[name] = (user, client)
    return {"society": society, "flats": flats, "users": users}


def user(world, name):
    return world["users"][name][0]


def api(world, name):
    return world["users"][name][1]


def flat_claims_url(world, label="A-101"):
    return reverse(
        "flat-claims",
        kwargs={"society_id": world["society"].id, "flat_id": world["flats"][label].id},
    )


def claim_url(world, route, claim):
    return reverse(
        route, kwargs={"society_id": world["society"].id, "claim_id": claim.id}
    )


def queue_url(world):
    return reverse("claim-list", kwargs={"society_id": world["society"].id})


def body(**overrides):
    return {
        "amount": "1500.00",
        "paid_on": today().isoformat(),
        "method": "upi",
        "reference": "UTR123",
        **overrides,
    }


def make_claim(world, who="res_a", label="A-101", amount="1500.00", **kwargs):
    claim, _ = submit_claim(
        society=world["society"],
        flat=world["flats"][label],
        claimant=user(world, who),
        amount=D(amount),
        paid_on=today(),
        method="upi",
        reference="UTR",
        **kwargs,
    )
    return claim


def owed(world, label="A-101"):
    return outstanding_for_flat(world["flats"][label])


def payments():
    return LedgerEntry.objects.filter(kind="payment")


# --- A claim is not money ---------------------------------------------------------------------


def test_a_claim_changes_no_balance_and_adds_no_ledger_entry(world):
    entries_before = LedgerEntry.objects.count()

    response = api(world, "res_a").post(flat_claims_url(world), body(), format="json")

    assert response.status_code == 201
    assert response.json()["status"] == "pending"
    assert owed(world) == D("4500.00")
    assert LedgerEntry.objects.count() == entries_before


def test_rejecting_or_withdrawing_never_touches_the_ledger(world):
    entries_before = LedgerEntry.objects.count()
    rejected = make_claim(world)
    withdrawn = make_claim(world)

    api(world, "treasurer").post(
        claim_url(world, "claim-reject", rejected), {"reason": "Not in the bank"}, format="json"
    )
    api(world, "res_a").post(claim_url(world, "claim-withdraw", withdrawn), {}, format="json")

    assert LedgerEntry.objects.count() == entries_before
    assert owed(world) == D("4500.00")


# --- Who may claim, and what -----------------------------------------------------------------


def test_a_resident_can_only_claim_for_the_flat_they_live_in(world):
    response = api(world, "res_a").post(flat_claims_url(world, "A-102"), body(), format="json")

    assert response.status_code == 404
    assert PaymentClaim.objects.count() == 0


def test_an_office_bearer_can_claim_for_their_own_flat(world):
    # They cannot record their own payment, so this is how it gets recorded by someone else.
    response = api(world, "secretary").post(flat_claims_url(world, "A-103"), body(), format="json")

    assert response.status_code == 201


def test_an_office_bearer_cannot_claim_for_a_flat_they_do_not_live_in(world):
    response = api(world, "treasurer").post(flat_claims_url(world, "A-101"), body(), format="json")

    assert response.status_code == 404


def test_the_service_checks_the_flat_too_not_only_the_view(world):
    with pytest.raises(services.NotYourFlat):
        submit_claim(
            society=world["society"], flat=world["flats"]["A-102"],
            claimant=user(world, "res_a"), amount=D("100"), paid_on=today(), method="upi",
        )


@pytest.mark.parametrize(
    "overrides, field",
    [
        ({"amount": "0"}, "amount"),
        ({"amount": "-5"}, "amount"),
        ({"amount": "10.005"}, "amount"),
        ({"amount": "abc"}, "amount"),
        ({"amount": "4500.01"}, "amount"),  # more than the flat owes
        ({"paid_on": (today() + timedelta(days=1)).isoformat()}, "paid_on"),
        ({"paid_on": (today() - timedelta(days=800)).isoformat()}, "paid_on"),
        ({"method": "bitcoin"}, "method"),
        ({"reference": "x" * 61}, "reference"),
    ],
)
def test_a_claim_that_makes_no_sense_is_refused_and_stores_nothing(world, overrides, field):
    response = api(world, "res_a").post(flat_claims_url(world), body(**overrides), format="json")

    assert response.status_code == 400
    assert field in response.json()
    assert PaymentClaim.objects.count() == 0


# --- The pending cap --------------------------------------------------------------------------


def test_a_flat_can_have_three_claims_waiting_and_no_more(world):
    for i in range(3):
        assert api(world, "res_a").post(
            flat_claims_url(world), body(amount=f"{100 + i}.00"), format="json"
        ).status_code == 201

    fourth = api(world, "res_a").post(flat_claims_url(world), body(amount="104.00"), format="json")

    assert fourth.status_code == 409
    assert fourth.json()["code"] == "too_many_pending"
    assert PaymentClaim.objects.count() == 3


def test_answering_a_claim_makes_room_for_another(world):
    claims = [make_claim(world, amount=f"{100 + i}.00") for i in range(3)]
    api(world, "treasurer").post(
        claim_url(world, "claim-reject", claims[0]), {"reason": "Wrong amount"}, format="json"
    )

    assert api(world, "res_a").post(
        flat_claims_url(world), body(amount="200.00"), format="json"
    ).status_code == 201


@pytest.mark.django_db(transaction=True)
def test_six_simultaneous_claims_leave_exactly_three_waiting(world, monkeypatch):
    """Proves: the flat row lock makes the cap check and the insert one step.

    Without it all six read "0 waiting", pass, and insert: six claims against a cap of three.
    """
    real = services.pending_count

    def slow(flat):  # widen the window between counting and inserting
        count = real(flat)
        time.sleep(0.05)
        return count

    monkeypatch.setattr(services, "pending_count", slow)

    def attempt(i):
        try:
            submit_claim(
                society=world["society"], flat=world["flats"]["A-101"],
                claimant=user(world, "res_a"), amount=D("100.00"), paid_on=today(),
                method="upi", idempotency_key=f"tap-{i}",
            )
            return "created"
        except TooManyPendingClaims:
            return "refused"

    results = run_in_parallel(6, attempt)

    assert results.count("created") == 3
    assert PaymentClaim.objects.filter(status="pending").count() == 3


# --- Double taps ------------------------------------------------------------------------------


def test_a_retry_with_the_same_key_returns_the_same_claim(world):
    first = api(world, "res_a").post(
        flat_claims_url(world), body(), format="json", headers={"Idempotency-Key": "k1"}
    )
    again = api(world, "res_a").post(
        flat_claims_url(world), body(), format="json", headers={"Idempotency-Key": "k1"}
    )

    assert (first.status_code, again.status_code) == (201, 200)
    assert first.json()["id"] == again.json()["id"]
    assert PaymentClaim.objects.count() == 1


def test_the_same_key_with_a_different_amount_is_a_conflict(world):
    api(world, "res_a").post(
        flat_claims_url(world), body(), format="json", headers={"Idempotency-Key": "k2"}
    )

    response = api(world, "res_a").post(
        flat_claims_url(world), body(amount="900.00"), format="json",
        headers={"Idempotency-Key": "k2"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "idempotency_key_reused"


# --- Who sees what ----------------------------------------------------------------------------


def test_a_resident_sees_their_own_flats_claims_and_nobody_elses(world):
    make_claim(world, "res_a", "A-101")
    make_claim(world, "res_b", "A-102")

    own = api(world, "res_a").get(flat_claims_url(world, "A-101"))
    other = api(world, "res_a").get(flat_claims_url(world, "A-102"))

    assert own.status_code == 200 and len(own.json()) == 1
    assert other.status_code == 404


def test_the_queue_is_for_office_bearers_only(world):
    make_claim(world)

    assert api(world, "res_a").get(queue_url(world)).status_code == 403
    for name in ("treasurer", "president", "secretary"):
        response = api(world, name).get(queue_url(world))
        assert response.status_code == 200 and len(response.json()) == 1


def test_the_queue_shows_waiting_claims_unless_asked_for_others(world):
    waiting = make_claim(world, amount="100.00")
    answered = make_claim(world, amount="200.00")
    api(world, "treasurer").post(
        claim_url(world, "claim-reject", answered), {"reason": "No"}, format="json"
    )

    default = api(world, "treasurer").get(queue_url(world)).json()
    everything = api(world, "treasurer").get(queue_url(world) + "?status=all").json()

    assert [c["id"] for c in default] == [waiting.id]
    assert len(everything) == 2
    assert api(world, "treasurer").get(queue_url(world) + "?status=bogus").status_code == 400


# --- Withdrawing ------------------------------------------------------------------------------


def test_the_person_who_claimed_can_withdraw(world):
    claim = make_claim(world)

    url = claim_url(world, "claim-withdraw", claim)
    response = api(world, "res_a").post(url, {}, format="json")

    assert response.status_code == 200
    assert response.json()["status"] == "withdrawn"


def test_nobody_else_can_withdraw_it(world):
    claim = make_claim(world)

    for name in ("res_b", "treasurer"):
        response = api(world, name).post(
            claim_url(world, "claim-withdraw", claim), {}, format="json"
        )
        assert response.status_code == 404
    claim.refresh_from_db()
    assert claim.status == "pending"


def test_a_withdrawn_claim_cannot_be_accepted(world):
    claim = make_claim(world)
    api(world, "res_a").post(claim_url(world, "claim-withdraw", claim), {}, format="json")

    url = claim_url(world, "claim-accept", claim)
    response = api(world, "treasurer").post(url, {}, format="json")

    assert response.status_code == 409
    assert response.json()["code"] == "claim_not_pending"
    assert payments().count() == 0


# --- Accepting --------------------------------------------------------------------------------


def test_accepting_records_the_payment_and_links_it_back(world):
    claim = make_claim(world, amount="1500.00")

    response = api(world, "treasurer").post(
        claim_url(world, "claim-accept", claim), {}, format="json"
    )

    assert response.status_code == 200
    claim.refresh_from_db()
    entry = claim.ledger_entry
    assert (claim.status, claim.resolved_by, claim.accepted_amount) == (
        "accepted", user(world, "treasurer"), D("1500.00"),
    )
    assert (entry.kind, entry.amount, entry.created_by) == (
        "payment", D("1500.00"), user(world, "treasurer"),
    )
    assert entry.idempotency_key == f"claim-{claim.pk}"
    assert entry.note == "Reported by resident: UPI UTR"  # plain words on the statement
    assert owed(world) == D("3000.00")
    actions = set(AuditLog.objects.values_list("action", flat=True))
    assert {"payment.recorded", "claim.accepted"} <= actions


def test_the_treasurer_can_record_what_the_bank_really_shows(world):
    claim = make_claim(world, amount="4500.00")

    response = api(world, "treasurer").post(
        claim_url(world, "claim-accept", claim), {"amount": "4050.00"}, format="json"
    )

    assert response.status_code == 200
    claim.refresh_from_db()
    assert (claim.amount, claim.accepted_amount) == (D("4500.00"), D("4050.00"))  # both kept
    assert claim.ledger_entry.amount == D("4050.00")
    assert owed(world) == D("450.00")


def test_a_claim_cannot_be_accepted_twice(world):
    claim = make_claim(world)
    api(world, "treasurer").post(claim_url(world, "claim-accept", claim), {}, format="json")

    again = api(world, "president").post(claim_url(world, "claim-accept", claim), {}, format="json")

    assert again.status_code == 409
    assert payments().count() == 1


@pytest.mark.django_db(transaction=True)
def test_two_office_bearers_accepting_at_once_record_exactly_one_payment(world, monkeypatch):
    """Proves: the claim row lock. The second to arrive waits, then finds it already answered.

    record_payment's own "claim-<id>" key would also stop a second payment, which is the point
    of having two layers. So this test asserts the CLAIM was answered once: without the claim
    lock both callers would report success.
    """
    claim = make_claim(world, amount="1500.00")
    real = services.record_payment

    def slow(**kwargs):
        time.sleep(0.2)
        return real(**kwargs)

    monkeypatch.setattr(services, "record_payment", slow)
    actors = [user(world, "treasurer"), user(world, "president")]

    def accept(i):
        try:
            accept_claim(society=world["society"], claim=claim, actor=actors[i])
            return "accepted"
        except ClaimNotPending:
            return "refused"

    results = run_in_parallel(2, accept)

    assert sorted(results) == ["accepted", "refused"]
    assert payments().count() == 1
    assert owed(world) == D("3000.00")


def test_nobody_answers_a_claim_for_the_flat_they_live_in(world):
    claim = make_claim(world, "secretary", "A-103", amount="1500.00")

    own = api(world, "secretary").post(claim_url(world, "claim-accept", claim), {}, format="json")
    own_reject = api(world, "secretary").post(
        claim_url(world, "claim-reject", claim), {"reason": "No"}, format="json"
    )
    other = api(world, "treasurer").post(claim_url(world, "claim-accept", claim), {}, format="json")

    assert (own.status_code, own_reject.status_code) == (403, 403)
    assert other.status_code == 200


def test_a_resident_cannot_answer_claims(world):
    claim = make_claim(world, "res_a", "A-101")

    for route, data in (("claim-accept", {}), ("claim-reject", {"reason": "No"})):
        response = api(world, "res_b").post(claim_url(world, route, claim), data, format="json")
        assert response.status_code == 403
    assert PaymentClaim.objects.get().status == "pending"


def test_accepting_more_than_is_owed_is_refused_and_the_claim_stays_waiting(world):
    claim = make_claim(world, amount="4500.00")
    record_payment(
        society=world["society"], flat=world["flats"]["A-101"], amount=D("4000.00"),
        actor=user(world, "president"),
    )  # paid most of it by hand in the meantime

    response = api(world, "treasurer").post(
        claim_url(world, "claim-accept", claim), {}, format="json"
    )

    assert response.status_code == 400
    claim.refresh_from_db()
    assert claim.status == "pending"
    assert payments().count() == 1  # only the manual one


def test_accepting_a_claim_already_recorded_by_hand_gets_the_duplicate_question(world):
    claim = make_claim(world, amount="1500.00")
    record_payment(
        society=world["society"], flat=world["flats"]["A-101"], amount=D("1500.00"),
        actor=user(world, "president"),
    )  # the treasurer already entered this payment manually

    asked = api(world, "treasurer").post(claim_url(world, "claim-accept", claim), {}, format="json")
    confirmed = api(world, "treasurer").post(
        claim_url(world, "claim-accept", claim), {"confirm_duplicate": True}, format="json"
    )

    assert asked.status_code == 409 and asked.json()["code"] == "possible_duplicate"
    assert confirmed.status_code == 200
    assert payments().count() == 2


def test_if_the_audit_write_fails_the_payment_and_the_claim_roll_back_together(world, monkeypatch):
    claim = make_claim(world, amount="1500.00")
    real = services.audit.record

    def fail_on_claim_audit(**kwargs):
        if kwargs["action"] == AuditLog.Action.CLAIM_ACCEPTED:
            raise RuntimeError("audit down")
        return real(**kwargs)

    monkeypatch.setattr(services.audit, "record", fail_on_claim_audit)

    with pytest.raises(RuntimeError):
        accept_claim(society=world["society"], claim=claim, actor=user(world, "treasurer"))

    claim.refresh_from_db()
    assert claim.status == "pending" and claim.ledger_entry is None
    assert payments().count() == 0  # the payment written a moment earlier is gone too
    assert owed(world) == D("4500.00")


# --- Rejecting --------------------------------------------------------------------------------


def test_rejecting_needs_a_reason_the_resident_can_read(world):
    claim = make_claim(world)

    blank = api(world, "treasurer").post(
        claim_url(world, "claim-reject", claim), {"reason": "  "}, format="json"
    )
    ok = api(world, "treasurer").post(
        claim_url(world, "claim-reject", claim), {"reason": "No such transfer in the bank"},
        format="json",
    )

    assert blank.status_code == 400
    assert ok.status_code == 200
    seen = api(world, "res_a").get(flat_claims_url(world)).json()[0]
    assert (seen["status"], seen["resolution_note"]) == ("rejected", "No such transfer in the bank")


def test_a_claim_is_rejected_once(world):
    claim = make_claim(world)
    api(world, "treasurer").post(
        claim_url(world, "claim-reject", claim), {"reason": "No"}, format="json"
    )

    again = api(world, "treasurer").post(
        claim_url(world, "claim-reject", claim), {"reason": "Still no"}, format="json"
    )

    assert again.status_code == 409


# --- The database's own rules -----------------------------------------------------------------


def _bad_claim(world, **fields):
    values = {
        "society": world["society"], "flat": world["flats"]["A-101"],
        "claimed_by": user(world, "res_a"), "amount": D("10.00"), "paid_on": today(),
        "method": "upi",
    }
    return PaymentClaim(**{**values, **fields})


@pytest.mark.parametrize(
    "fields",
    [
        {"amount": D("0")},
        {"status": "accepted"},  # accepted, but no payment and no resolver
        {"status": "rejected"},  # rejected, but no reason
        {"status": "pending", "resolved_at": None, "resolution_note": "", "accepted_amount": None,
         "resolved_by_id": "RESOLVER"},  # waiting, yet already "resolved"
        {"status": "nonsense"},
        {"method": "barter"},
    ],
)
def test_the_database_refuses_an_impossible_claim(world, fields):
    fields = {
        k: (user(world, "treasurer").pk if v == "RESOLVER" else v) for k, v in fields.items()
    }
    claim = _bad_claim(world, **fields)

    with pytest.raises(IntegrityError), transaction.atomic():
        claim.save()


# --- Another society -----------------------------------------------------------------------------


def test_another_societys_claim_is_indistinguishable_from_one_that_does_not_exist(world):
    other = Society.objects.create(name="Lake View", slug="lake-view")
    their_flat = Flat.objects.create(society=other, label="B-1")
    record_charge(society=other, flat=their_flat, amount=D("100.00"))
    their_resident = get_user_model().objects.create_user(username="b_res", password="x")
    add_member(society=other, user=their_resident, role="resident", flat=their_flat)
    theirs = submit_claim(
        society=other, flat=their_flat, claimant=their_resident, amount=D("50"),
        paid_on=today(), method="upi",
    )[0]
    missing = PaymentClaim(pk=999_999)

    for route, data in (
        ("claim-accept", {}), ("claim-reject", {"reason": "x"}), ("claim-withdraw", {}),
    ):
        foreign = api(world, "treasurer").post(claim_url(world, route, theirs), data, format="json")
        absent = api(world, "treasurer").post(claim_url(world, route, missing), data, format="json")
        assert foreign.status_code == absent.status_code == 404
        assert foreign.json() == absent.json()
    theirs.refresh_from_db()
    assert theirs.status == "pending"
    assert api(world, "treasurer").get(queue_url(world)).json() == []
