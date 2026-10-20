"""Segregation of duties: nobody records or reverses payments for the flat they live in.

Office-bearers are also residents who pay dues. These tests prove the control cannot be dodged
by role, by sharing a flat, or by reversing instead of recording, and that a refusal writes
nothing.
"""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from apps.audit.models import AuditLog
from apps.ledger.models import LedgerEntry
from apps.ledger.selectors import outstanding_for_flat
from apps.ledger.services import (
    SelfPaymentNotAllowed,
    record_charge,
    record_payment,
    reverse_entry,
)
from apps.societies.models import Flat, Society
from apps.societies.services import add_member

pytestmark = pytest.mark.django_db

D = Decimal
OFFICE = ["president", "secretary", "treasurer"]


@pytest.fixture
def world():
    society = Society.objects.create(name="Green Park", slug="green-park")
    flats, people = {}, {}
    # Every office-bearer lives in their own flat; one plain resident too.
    for name, role in [
        ("president", "president"),
        ("secretary", "secretary"),
        ("treasurer", "treasurer"),
        ("resident", "resident"),
    ]:
        flats[name] = Flat.objects.create(society=society, label=f"F-{name[:3]}")
        user = get_user_model().objects.create_user(username=name, password="x")
        add_member(society=society, user=user, role=role, flat=flats[name])
        people[name] = user
        record_charge(society=society, flat=flats[name], amount=D("100.00"))
    return {"society": society, "flats": flats, "people": people}


def api(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def pay_url(world, flat):
    return reverse(
        "payment-create", kwargs={"society_id": world["society"].id, "flat_id": flat.id}
    )


def reverse_url(world, entry):
    return reverse(
        "entry-reverse", kwargs={"society_id": world["society"].id, "entry_id": entry.id}
    )


def pay(world, who, flat_of, amount="10.00"):
    """`who` records a payment for the flat that `flat_of` lives in."""
    return record_payment(
        society=world["society"],
        flat=world["flats"][flat_of],
        amount=D(amount),
        actor=world["people"][who],
    )


# --- Recording ------------------------------------------------------------------------------


@pytest.mark.parametrize("who", OFFICE)
def test_nobody_may_record_a_payment_for_their_own_flat(world, who):
    """Proves: the treasurer, secretary AND president are all refused on their own flat."""
    response = api(world["people"][who]).post(
        pay_url(world, world["flats"][who]), {"amount": "10.00"}, format="json"
    )

    assert response.status_code == 403
    assert "flat you live in" in response.json()["detail"]
    assert outstanding_for_flat(world["flats"][who]) == D("100.00")


@pytest.mark.parametrize("who", OFFICE)
def test_a_refusal_writes_no_ledger_row_and_no_audit_row(world, who):
    before = (LedgerEntry.objects.count(), AuditLog.objects.count())

    with pytest.raises(SelfPaymentNotAllowed):
        pay(world, who, who)

    assert (LedgerEntry.objects.count(), AuditLog.objects.count()) == before


@pytest.mark.parametrize(
    ("recorder", "target"),
    [
        ("secretary", "treasurer"),  # the case the rule exists for
        ("president", "treasurer"),
        ("treasurer", "secretary"),
        ("treasurer", "president"),
        ("treasurer", "resident"),
        ("secretary", "resident"),
        ("president", "secretary"),
    ],
)
def test_another_office_bearer_can_record_for_someone_elses_flat(world, recorder, target):
    entry, created = pay(world, recorder, target)

    assert created is True
    assert outstanding_for_flat(world["flats"][target]) == D("90.00")
    assert entry.created_by == world["people"][recorder]


def test_anyone_who_shares_the_flat_is_refused_too(world):
    """A second office-bearer living in the treasurer's flat cannot credit that flat either."""
    housemate = get_user_model().objects.create_user(username="housemate", password="x")
    add_member(
        society=world["society"], user=housemate, role="president", flat=world["flats"]["treasurer"]
    )

    response = api(housemate).post(
        pay_url(world, world["flats"]["treasurer"]), {"amount": "10.00"}, format="json"
    )

    assert response.status_code == 403
    # ...but they can still serve everyone else.
    other = api(housemate).post(
        pay_url(world, world["flats"]["resident"]), {"amount": "10.00"}, format="json"
    )
    assert other.status_code == 201


def test_the_refusal_cannot_be_dodged_with_an_idempotency_key(world):
    response = api(world["people"]["treasurer"]).post(
        pay_url(world, world["flats"]["treasurer"]),
        {"amount": "10.00"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="sneaky-1",
    )

    assert response.status_code == 403
    assert not LedgerEntry.objects.filter(idempotency_key="sneaky-1").exists()


# --- Reversing ------------------------------------------------------------------------------


@pytest.mark.parametrize("who", OFFICE)
def test_nobody_may_reverse_a_payment_on_their_own_flat(world, who):
    other = "resident"
    payment, _ = pay(world, other if who != "president" else "treasurer", who)

    response = api(world["people"][who]).post(reverse_url(world, payment), {}, format="json")

    assert response.status_code == 403
    assert not LedgerEntry.objects.filter(reverses=payment).exists()


def test_nobody_may_cancel_a_charge_on_their_own_flat(world):
    """Cancelling your own charge reduces what you owe, so it is just as much a conflict."""
    charge = LedgerEntry.objects.get(flat=world["flats"]["treasurer"], kind="charge")

    with pytest.raises(SelfPaymentNotAllowed):
        reverse_entry(society=world["society"], entry=charge, actor=world["people"]["treasurer"])

    assert outstanding_for_flat(world["flats"]["treasurer"]) == D("100.00")


def test_another_office_bearer_can_reverse_the_treasurers_payment(world):
    payment, _ = pay(world, "secretary", "treasurer", "40.00")

    response = api(world["people"]["president"]).post(
        reverse_url(world, payment), {}, format="json"
    )

    assert response.status_code == 201
    assert outstanding_for_flat(world["flats"]["treasurer"]) == D("100.00")


def test_a_refused_reversal_writes_nothing(world):
    payment, _ = pay(world, "secretary", "treasurer")
    before = (LedgerEntry.objects.count(), AuditLog.objects.count())

    with pytest.raises(SelfPaymentNotAllowed):
        reverse_entry(society=world["society"], entry=payment, actor=world["people"]["treasurer"])

    assert (LedgerEntry.objects.count(), AuditLog.objects.count()) == before


# --- Scope: the rule is about the actor's OWN flat only ----------------------------------------


def test_living_in_another_society_does_not_block_you_here(world):
    """A person who lives in a flat of society B is not restricted in society A."""
    other = Society.objects.create(name="Lake View", slug="lake-view")
    own_flat_there = Flat.objects.create(society=other, label="X-1")
    visitor = get_user_model().objects.create_user(username="visitor", password="x")
    add_member(society=other, user=visitor, role="resident", flat=own_flat_there)
    add_member(
        society=world["society"], user=visitor, role="treasurer", flat=world["flats"]["resident"]
    )

    entry, created = record_payment(
        society=world["society"], flat=world["flats"]["president"], amount=D("5.00"), actor=visitor
    )

    assert created is True and entry.created_by == visitor


def test_an_office_bearer_with_no_flat_can_record_for_anyone(world):
    """A secretary who does not live in the society is not blocked anywhere."""
    outsider = get_user_model().objects.create_user(username="outsider", password="x")
    add_member(society=world["society"], user=outsider, role="secretary")

    for flat in world["flats"].values():
        entry, created = record_payment(
            society=world["society"], flat=flat, amount=D("1.00"), actor=outsider
        )
        assert created is True
