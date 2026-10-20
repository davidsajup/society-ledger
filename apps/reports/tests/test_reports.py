from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework.test import APIClient

from apps.expenses.services import record_expense
from apps.ledger.models import LedgerEntry
from apps.ledger.selectors import outstanding_for_flat
from apps.ledger.services import record_charge, record_payment, reverse_entry
from apps.reports.selectors import society_summary
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
    a = Flat.objects.create(society=society, label="A-1", monthly_maintenance=D("100.00"))
    b = Flat.objects.create(society=society, label="B-1", monthly_maintenance=D("200.00"))
    quiet = Flat.objects.create(society=society, label="C-1")
    people = {}
    for name, role, flat in [("admin", "secretary", None), ("treasurer", "treasurer", None),
                             ("resident", "resident", a)]:
        user = get_user_model().objects.create_user(username=name, password="x")
        add_member(society=society, user=user, role=role, flat=flat)
        people[name] = user
    return {"society": society, "a": a, "b": b, "quiet": quiet, "people": people}


def url(world, name):
    return reverse(name, kwargs={"society_id": world["society"].id})


def flat_row(summary, flat):
    return next(row for row in summary["flats"] if row["id"] == flat.id)


# --- Summary numbers ------------------------------------------------------------------------


def test_summary_adds_up_and_includes_flats_with_no_entries(world):
    s, tr = world["society"], world["people"]["treasurer"]
    record_charge(society=s, flat=world["a"], amount=D("300.00"))
    record_charge(society=s, flat=world["b"], amount=D("200.00"))
    record_payment(society=s, flat=world["a"], amount=D("100.00"), actor=tr)
    record_expense(society=s, actor=tr, category="repairs", description="Pump",
                   amount=D("50.00"), paid_on=date(2026, 10, 1))

    summary = society_summary(s)

    assert summary["totals"] == {
        "billed": D("500.00"), "collected": D("100.00"), "outstanding": D("400.00"),
        "spent": D("50.00"),
    }
    assert flat_row(summary, world["a"])["outstanding"] == D("200.00")
    assert flat_row(summary, world["quiet"]) == {
        "id": world["quiet"].id, "label": "C-1", "billed": D("0.00"),
        "collected": D("0.00"), "outstanding": D("0.00"),
    }
    assert [r["label"] for r in summary["flats"]] == ["A-1", "B-1", "C-1"]


def test_a_reversed_payment_is_not_double_counted_as_billing(world):
    """Reversing a payment appends a charge row. Net figures must show it as 'less collected',
    not as 'more billed'."""
    s, tr = world["society"], world["people"]["treasurer"]
    record_charge(society=s, flat=world["a"], amount=D("100.00"))
    payment, _ = record_payment(society=s, flat=world["a"], amount=D("100.00"), actor=tr)
    reverse_entry(society=s, entry=payment, actor=tr)

    totals = society_summary(s)["totals"]

    assert (totals["billed"], totals["collected"], totals["outstanding"]) == (
        D("100.00"), D("0.00"), D("100.00"),
    )


def test_a_reversed_charge_reduces_billing(world):
    s, tr = world["society"], world["people"]["treasurer"]
    charge = record_charge(society=s, flat=world["a"], amount=D("100.00"))
    reverse_entry(society=s, entry=charge, actor=tr)

    totals = society_summary(s)["totals"]

    assert (totals["billed"], totals["outstanding"]) == (D("0.00"), D("0.00"))


def test_summary_never_includes_another_societys_money(world):
    other = Society.objects.create(name="Lake View", slug="lake-view")
    foreign = Flat.objects.create(society=other, label="X-1")
    record_charge(society=other, flat=foreign, amount=D("9999.00"))
    record_charge(society=world["society"], flat=world["a"], amount=D("100.00"))

    summary = society_summary(world["society"])

    assert summary["totals"]["billed"] == D("100.00")
    assert all(row["label"] != "X-1" for row in summary["flats"])


def test_summary_outstanding_matches_the_ledger_balance_per_flat(world):
    s, tr = world["society"], world["people"]["treasurer"]
    for flat, amount in ((world["a"], "300.00"), (world["b"], "50.50")):
        record_charge(society=s, flat=flat, amount=D(amount))
    record_payment(society=s, flat=world["a"], amount=D("120.25"), actor=tr)

    summary = society_summary(s)

    for flat in (world["a"], world["b"], world["quiet"]):
        assert flat_row(summary, flat)["outstanding"] == outstanding_for_flat(flat)


# --- Endpoints ------------------------------------------------------------------------------


def test_summary_endpoint_returns_exact_strings(world):
    record_charge(society=world["society"], flat=world["a"], amount=D("1500.50"))

    response = client_for(world["people"]["treasurer"]).get(url(world, "summary"))

    assert response.status_code == 200
    body = response.json()
    assert body["totals"]["billed"] == "1500.50"  # a string, not the float 1500.5
    assert body["totals"]["spent"] == "0.00"
    assert body["flats"][0]["label"] == "A-1"


@pytest.mark.parametrize("name", ["summary", "activity"])
def test_residents_cannot_read_society_wide_reports(world, name):
    assert client_for(world["people"]["resident"]).get(url(world, name)).status_code == 403


@pytest.mark.parametrize("name", ["summary", "activity"])
@pytest.mark.parametrize("who", ["admin", "treasurer"])
def test_admin_and_treasurer_can_read_reports(world, name, who):
    assert client_for(world["people"][who]).get(url(world, name)).status_code == 200


def test_activity_lists_newest_payments_with_reversal_flags(world):
    s, tr = world["society"], world["people"]["treasurer"]
    record_charge(society=s, flat=world["a"], amount=D("300.00"))
    first, _ = record_payment(society=s, flat=world["a"], amount=D("100.00"), actor=tr)
    record_payment(society=s, flat=world["a"], amount=D("50.00"), actor=tr)
    reverse_entry(society=s, entry=first, actor=tr)

    rows = client_for(tr).get(url(world, "activity")).json()

    assert [(r["amount"], r["reversed"], r["is_reversal"]) for r in rows] == [
        ("50.00", False, False),
        ("100.00", True, False),
    ]
    assert rows[0]["flat_label"] == "A-1" and rows[0]["recorded_by"] == "treasurer"


def test_activity_excludes_charges_and_other_societies(world):
    other = Society.objects.create(name="Lake View", slug="lake-view")
    foreign = Flat.objects.create(society=other, label="X-1")
    tr = world["people"]["treasurer"]
    record_charge(society=other, flat=foreign, amount=D("100.00"))
    record_payment(society=other, flat=foreign, amount=D("100.00"), actor=tr)
    record_charge(society=world["society"], flat=world["a"], amount=D("100.00"))

    assert client_for(tr).get(url(world, "activity")).json() == []


def test_reports_run_a_constant_number_of_queries(world):
    s, tr = world["society"], world["people"]["treasurer"]
    record_charge(society=s, flat=world["a"], amount=D("1000.00"))
    client = client_for(tr)

    def count(name):
        with CaptureQueriesContext(connection) as ctx:
            assert client.get(url(world, name)).status_code == 200
        return len(ctx)

    baselines = {name: count(name) for name in ("summary", "activity")}
    for i in range(5):
        flat = Flat.objects.create(society=s, label=f"N-{i}")
        record_charge(society=s, flat=flat, amount=D("10.00"))
        record_payment(society=s, flat=flat, amount=D("10.00"), actor=tr)

    assert {name: count(name) for name in ("summary", "activity")} == baselines


def test_reports_are_read_only_over_http(world):
    client = client_for(world["people"]["treasurer"])
    before = LedgerEntry.objects.count()

    for name in ("summary", "activity"):
        for method in ("post", "put", "patch", "delete"):
            assert getattr(client, method)(url(world, name), {}).status_code == 403
    assert LedgerEntry.objects.count() == before
