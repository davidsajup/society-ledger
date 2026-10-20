from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework.test import APIClient

from apps.audit.models import AuditLog
from apps.expenses.models import Expense
from apps.ledger.models import LedgerEntry
from apps.ledger.services import record_payment
from apps.societies.models import Flat, Society
from apps.societies.services import add_member

pytestmark = pytest.mark.django_db

D = Decimal
BODY = {
    "category": "repairs",
    "description": "Lift motor",
    "amount": "5000.50",
    "paid_on": "2026-10-01",
}


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def world():
    society = Society.objects.create(name="Green Park", slug="green-park")
    flat = Flat.objects.create(society=society, label="A-101", monthly_maintenance=D("100.00"))
    people = {}
    for name, role, own_flat in [
        ("admin", "secretary", None),
        ("treasurer", "treasurer", None),
        ("resident", "resident", flat),
    ]:
        user = get_user_model().objects.create_user(username=name, password="x")
        add_member(society=society, user=user, role=role, flat=own_flat)
        people[name] = (user, client_for(user))
    return {"society": society, "flat": flat, "people": people}


def who(world, name):
    return world["people"][name][1]


def list_url(world):
    return reverse("expense-list", kwargs={"society_id": world["society"].id})


def reverse_url(world, expense):
    return reverse(
        "expense-reverse", kwargs={"society_id": world["society"].id, "expense_id": expense.id}
    )


def audit_url(world):
    return reverse("audit-list", kwargs={"society_id": world["society"].id})


# --- Expenses ---------------------------------------------------------------------------------


def test_treasurer_records_an_expense_and_the_total_is_an_exact_string(world):
    response = who(world, "treasurer").post(list_url(world), BODY, format="json")

    assert response.status_code == 201
    assert response.json()["amount"] == "5000.50"
    listing = who(world, "treasurer").get(list_url(world)).json()
    assert listing["total_spent"] == "5000.50"  # string on the wire, not the float 5000.5
    assert [e["description"] for e in listing["expenses"]] == ["Lift motor"]


@pytest.mark.parametrize("name", ["admin", "resident"])
def test_only_the_treasurer_can_record_expenses(world, name):
    assert who(world, name).post(list_url(world), BODY, format="json").status_code == 403
    assert not Expense.objects.exists()


def test_admin_can_read_expenses_but_a_resident_cannot(world):
    who(world, "treasurer").post(list_url(world), BODY, format="json")

    assert who(world, "admin").get(list_url(world)).status_code == 200
    assert who(world, "resident").get(list_url(world)).status_code == 403


@pytest.mark.parametrize(
    "patch",
    [
        {"amount": "0"}, {"amount": "-1"}, {"amount": "1.005"}, {"amount": "abc"},
        {"category": "yacht"}, {"description": ""}, {"paid_on": "not-a-date"},
        {"paid_on": "2999-01-01"},
    ],
)
def test_bad_expense_input_is_400(world, patch):
    response = who(world, "treasurer").post(list_url(world), {**BODY, **patch}, format="json")

    assert response.status_code == 400
    assert not Expense.objects.exists()


def test_retry_with_the_same_key_returns_200_and_records_once(world):
    treasurer = who(world, "treasurer")
    headers = {"HTTP_IDEMPOTENCY_KEY": "exp-1"}

    first = treasurer.post(list_url(world), BODY, format="json", **headers)
    second = treasurer.post(list_url(world), BODY, format="json", **headers)

    assert (first.status_code, second.status_code) == (201, 200)
    assert first.json()["id"] == second.json()["id"]
    assert Expense.objects.count() == 1


def test_same_key_with_a_different_body_is_409(world):
    treasurer = who(world, "treasurer")
    treasurer.post(list_url(world), BODY, format="json", HTTP_IDEMPOTENCY_KEY="exp-1")

    response = treasurer.post(
        list_url(world), {**BODY, "amount": "1.00"}, format="json", HTTP_IDEMPOTENCY_KEY="exp-1"
    )

    assert response.status_code == 409


def test_treasurer_reverses_an_expense_and_the_total_returns_to_zero(world):
    treasurer = who(world, "treasurer")
    created = treasurer.post(list_url(world), BODY, format="json").json()
    expense = Expense.objects.get(pk=created["id"])

    response = treasurer.post(reverse_url(world, expense), {}, format="json")

    assert response.status_code == 201
    assert response.json()["reverses"] == expense.id
    assert treasurer.get(list_url(world)).json()["total_spent"] == "0.00"
    assert treasurer.post(reverse_url(world, expense), {}, format="json").status_code == 409


def test_expenses_cannot_be_edited_or_deleted_over_http(world):
    treasurer = who(world, "treasurer")
    created = treasurer.post(list_url(world), BODY, format="json").json()
    expense = Expense.objects.get(pk=created["id"])

    for method in ("put", "patch", "delete"):
        response = getattr(treasurer, method)(reverse_url(world, expense), {}, format="json")
        assert response.status_code == 403
    expense.refresh_from_db()
    assert expense.amount == D("5000.50")


# --- Audit log --------------------------------------------------------------------------------


def test_every_money_action_shows_up_in_the_audit_endpoint(world):
    treasurer_user, treasurer = world["people"]["treasurer"]
    LedgerEntry.objects.create(
        society=world["society"], flat=world["flat"], kind="charge", amount=D("100.00")
    )
    record_payment(
        society=world["society"], flat=world["flat"], amount=D("40.00"), actor=treasurer_user
    )
    treasurer.post(list_url(world), BODY, format="json")

    rows = who(world, "admin").get(audit_url(world)).json()

    assert [r["action"] for r in rows] == ["expense.recorded", "payment.recorded"]  # newest first
    assert {r["actor"] for r in rows} == {"treasurer"}
    assert rows[0]["amount"] == "5000.50"


def test_residents_cannot_read_the_audit_log(world):
    assert who(world, "resident").get(audit_url(world)).status_code == 403


def test_the_audit_log_cannot_be_written_over_http(world):
    for method in ("post", "put", "patch", "delete"):
        response = getattr(who(world, "treasurer"), method)(audit_url(world), {}, format="json")
        assert response.status_code == 403
    assert not AuditLog.objects.exists()


def test_the_audit_log_only_shows_this_societys_rows(world):
    treasurer_user, _ = world["people"]["treasurer"]
    other = Society.objects.create(name="Lake View", slug="lake-view")
    other_flat = Flat.objects.create(society=other, label="B-1")
    LedgerEntry.objects.create(society=other, flat=other_flat, kind="charge", amount=D("9.00"))
    record_payment(society=other, flat=other_flat, amount=D("9.00"), actor=treasurer_user)

    assert who(world, "admin").get(audit_url(world)).json() == []


def test_audit_list_runs_a_constant_number_of_queries(world):
    treasurer_user, _ = world["people"]["treasurer"]
    admin = who(world, "admin")
    LedgerEntry.objects.create(
        society=world["society"], flat=world["flat"], kind="charge", amount=D("500.00")
    )

    def count_queries():
        with CaptureQueriesContext(connection) as ctx:
            assert admin.get(audit_url(world)).status_code == 200
        return len(ctx)

    baseline = count_queries()
    for _ in range(5):
        record_payment(
            society=world["society"], flat=world["flat"], amount=D("1.00"), actor=treasurer_user
        )

    assert count_queries() == baseline
