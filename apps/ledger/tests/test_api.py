from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from apps.ledger.models import LedgerEntry
from apps.ledger.selectors import outstanding_for_flat
from apps.ledger.services import record_charge, record_payment
from apps.societies.models import Flat, Society
from apps.societies.services import add_member

pytestmark = pytest.mark.django_db

D = Decimal


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def world():
    society = Society.objects.create(name="Green Park", slug="green-park")
    flat = Flat.objects.create(society=society, label="A-101")
    neighbour_flat = Flat.objects.create(society=society, label="A-102")
    users = {}
    for name, role, own_flat in [
        ("admin", "admin", None),
        ("treasurer", "treasurer", None),
        ("resident", "resident", flat),
        ("neighbour", "resident", neighbour_flat),
    ]:
        user = get_user_model().objects.create_user(username=name, password="x")
        add_member(society=society, user=user, role=role, flat=own_flat)
        users[name] = (user, client_for(user))
    record_charge(society=society, flat=flat, amount=D("100.00"))
    record_charge(society=society, flat=neighbour_flat, amount=D("55.00"))
    return {"society": society, "flat": flat, "neighbour_flat": neighbour_flat, "users": users}


def client(world, name):
    return world["users"][name][1]


def pay_url(world, flat=None):
    flat = flat or world["flat"]
    return reverse(
        "payment-create", kwargs={"society_id": world["society"].id, "flat_id": flat.id}
    )


def ledger_url(world, flat=None):
    flat = flat or world["flat"]
    return reverse("flat-ledger", kwargs={"society_id": world["society"].id, "flat_id": flat.id})


def reverse_url(world, entry):
    return reverse(
        "entry-reverse", kwargs={"society_id": world["society"].id, "entry_id": entry.id}
    )


# --- Recording payments ---------------------------------------------------------------------


def test_treasurer_records_a_payment(world):
    response = client(world, "treasurer").post(pay_url(world), {"amount": "30.00"}, format="json")

    assert response.status_code == 201
    assert response.data["kind"] == "payment"
    assert response.json()["amount"] == "30.00"  # a string on the wire, never a float
    assert outstanding_for_flat(world["flat"]) == D("70.00")


@pytest.mark.parametrize("who", ["admin", "resident"])
def test_only_the_treasurer_can_record_payments(world, who):
    response = client(world, who).post(pay_url(world), {"amount": "30.00"}, format="json")

    assert response.status_code == 403
    assert outstanding_for_flat(world["flat"]) == D("100.00")


@pytest.mark.parametrize("bad", ["0", "-5", "0.001", "30.005", "abc", "", None, "1e400"])
def test_bad_amounts_are_rejected_with_400(world, bad):
    response = client(world, "treasurer").post(pay_url(world), {"amount": bad}, format="json")

    assert response.status_code == 400
    assert outstanding_for_flat(world["flat"]) == D("100.00")


def test_missing_amount_is_400(world):
    assert client(world, "treasurer").post(pay_url(world), {}, format="json").status_code == 400


def test_overpayment_is_400_and_writes_nothing(world):
    response = client(world, "treasurer").post(pay_url(world), {"amount": "100.01"}, format="json")

    assert response.status_code == 400
    assert "amount" in response.data
    assert not LedgerEntry.objects.filter(kind="payment").exists()


def test_json_number_amount_is_parsed_exactly(world):
    """30.1 sent as a JSON number must be stored as exactly 30.10, not 30.100000000000001."""
    response = client(world, "treasurer").post(pay_url(world), {"amount": 30.1}, format="json")

    assert response.status_code == 201
    assert LedgerEntry.objects.get(pk=response.data["id"]).amount == D("30.10")


def test_payment_for_a_flat_id_outside_the_society_is_404(world):
    other = Society.objects.create(name="Lake View", slug="lake-view")
    foreign = Flat.objects.create(society=other, label="B-1")
    record_charge(society=other, flat=foreign, amount=D("50.00"))

    response = client(world, "treasurer").post(
        pay_url(world, flat=foreign), {"amount": "10.00"}, format="json"
    )

    assert response.status_code == 404
    assert outstanding_for_flat(foreign) == D("50.00")


# --- Idempotency over HTTP ------------------------------------------------------------------


def test_retry_with_same_idempotency_key_returns_200_and_records_once(world):
    treasurer = client(world, "treasurer")
    headers = {"HTTP_IDEMPOTENCY_KEY": "abc-123"}

    first = treasurer.post(pay_url(world), {"amount": "30.00"}, format="json", **headers)
    second = treasurer.post(pay_url(world), {"amount": "30.00"}, format="json", **headers)

    assert (first.status_code, second.status_code) == (201, 200)
    assert first.data["id"] == second.data["id"]
    assert outstanding_for_flat(world["flat"]) == D("70.00")


def test_same_key_with_a_different_amount_is_409(world):
    treasurer = client(world, "treasurer")
    headers = {"HTTP_IDEMPOTENCY_KEY": "abc-123"}
    treasurer.post(pay_url(world), {"amount": "30.00"}, format="json", **headers)

    response = treasurer.post(pay_url(world), {"amount": "40.00"}, format="json", **headers)

    assert response.status_code == 409


def test_overlong_idempotency_key_is_400(world):
    response = client(world, "treasurer").post(
        pay_url(world), {"amount": "1.00"}, format="json", HTTP_IDEMPOTENCY_KEY="k" * 65
    )

    assert response.status_code == 400


# --- Reading a ledger: object-level permission ----------------------------------------------


def test_resident_reads_their_own_flats_ledger(world):
    response = client(world, "resident").get(ledger_url(world))

    assert response.status_code == 200
    assert response.json()["outstanding"] == "100.00"  # exact string, not the float 100.0
    assert response.json()["flat"]["label"] == "A-101"
    assert len(response.json()["entries"]) == 1


def test_resident_cannot_read_a_neighbours_ledger_and_cannot_tell_it_exists(world):
    """Object-level permission: same society, different flat -> 404, identical to a missing id."""
    resident = client(world, "resident")

    neighbour = resident.get(ledger_url(world, flat=world["neighbour_flat"]))
    missing_url = reverse(
        "flat-ledger", kwargs={"society_id": world["society"].id, "flat_id": 999_999}
    )
    missing = resident.get(missing_url)

    assert neighbour.status_code == missing.status_code == 404
    assert neighbour.data == missing.data
    assert "55.00" not in neighbour.content.decode()


@pytest.mark.parametrize("who", ["admin", "treasurer"])
def test_admin_and_treasurer_can_read_any_flats_ledger(world, who):
    response = client(world, who).get(ledger_url(world, flat=world["neighbour_flat"]))

    assert response.status_code == 200
    assert response.json()["outstanding"] == "55.00"


def test_ledger_lists_newest_entries_first_and_balance_matches(world):
    treasurer = client(world, "treasurer")
    treasurer.post(pay_url(world), {"amount": "30.00"}, format="json")

    data = client(world, "resident").get(ledger_url(world)).json()

    assert [e["kind"] for e in data["entries"]] == ["payment", "charge"]
    assert data["outstanding"] == "70.00"


# --- Reversals over HTTP --------------------------------------------------------------------


def test_treasurer_reverses_a_payment(world):
    payment, _ = record_payment(
        society=world["society"],
        flat=world["flat"],
        amount=D("100.00"),
        actor=world["users"]["treasurer"][0],
    )

    response = client(world, "treasurer").post(
        reverse_url(world, payment), {"note": "cheque bounced"}, format="json"
    )

    assert response.status_code == 201
    assert response.data["kind"] == "charge"
    assert response.data["reverses"] == payment.id
    assert outstanding_for_flat(world["flat"]) == D("100.00")


def test_reversing_twice_is_409(world):
    payment, _ = record_payment(
        society=world["society"],
        flat=world["flat"],
        amount=D("10.00"),
        actor=world["users"]["treasurer"][0],
    )
    treasurer = client(world, "treasurer")
    treasurer.post(reverse_url(world, payment), {}, format="json")

    assert treasurer.post(reverse_url(world, payment), {}, format="json").status_code == 409


@pytest.mark.parametrize("who", ["admin", "resident"])
def test_only_the_treasurer_can_reverse(world, who):
    entry = LedgerEntry.objects.filter(flat=world["flat"]).first()

    assert client(world, who).post(reverse_url(world, entry), {}, format="json").status_code == 403


def test_ledger_entries_cannot_be_edited_or_deleted_over_http(world):
    entry = LedgerEntry.objects.filter(flat=world["flat"]).first()
    url = reverse_url(world, entry)
    treasurer = client(world, "treasurer")

    for method in ("put", "patch", "delete"):
        assert getattr(treasurer, method)(url, {"amount": "1.00"}, format="json").status_code == 403
    entry.refresh_from_db()
    assert entry.amount == D("100.00")
