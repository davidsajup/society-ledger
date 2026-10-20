from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework.test import APIClient

from apps.billing.services import run_billing
from apps.ledger.models import LedgerEntry
from apps.ledger.selectors import outstanding_for_flat
from apps.ledger.services import record_charge, record_payment, reverse_entry
from apps.reports.dues import dues_grid
from apps.societies.models import Flat, Society
from apps.societies.services import add_member

pytestmark = pytest.mark.django_db

D = Decimal
AUG, SEP, OCT = date(2026, 8, 1), date(2026, 9, 1), date(2026, 10, 1)


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def world():
    society = Society.objects.create(name="Green Park", slug="green-park")
    flat = Flat.objects.create(society=society, label="A-1", monthly_maintenance=D("1500.00"))
    other = Flat.objects.create(society=society, label="B-1", monthly_maintenance=D("1000.00"))
    quiet = Flat.objects.create(society=society, label="C-1")  # not billed
    people = {}
    for name, role, own in [("admin", "admin", None), ("treasurer", "treasurer", None),
                            ("resident", "resident", flat)]:
        user = get_user_model().objects.create_user(username=name, password="x")
        add_member(society=society, user=user, role=role, flat=own)
        people[name] = user
    return {"society": society, "a": flat, "b": other, "quiet": quiet, "people": people}


def bill(world, *periods):
    for period in periods:
        run_billing(society=world["society"], period=period)


def pay(world, flat, amount):
    entry, _ = record_payment(
        society=world["society"], flat=flat, amount=D(amount), actor=world["people"]["treasurer"]
    )
    return entry


def row(grid, flat):
    return next(r for r in grid["flats"] if r["id"] == flat.id)


def cells(grid, flat):
    return {c["period"]: c for c in row(grid, flat)["cells"]}


# --- The allocation rule: oldest dues are paid first ------------------------------------------


def test_payments_clear_the_oldest_month_first(world):
    bill(world, AUG, SEP, OCT)
    pay(world, world["a"], "2250.00")  # = Aug in full + half of Sep

    c = cells(dues_grid(world["society"]), world["a"])

    assert (c[AUG]["status"], c[AUG]["due"]) == ("paid", D("0.00"))
    sep = (c[SEP]["status"], c[SEP]["paid"], c[SEP]["due"])
    assert sep == ("partial", D("750.00"), D("750.00"))
    assert (c[OCT]["status"], c[OCT]["due"]) == ("unpaid", D("1500.00"))


def test_unpaid_flat_shows_every_month_unpaid_and_unbilled_flat_shows_none(world):
    bill(world, AUG, SEP)

    grid = dues_grid(world["society"])

    assert [c["status"] for c in row(grid, world["b"])["cells"]] == ["unpaid", "unpaid"]
    assert [c["status"] for c in row(grid, world["quiet"])["cells"]] == ["none", "none"]
    assert row(grid, world["quiet"])["outstanding"] == D("0.00")


def test_periods_are_listed_oldest_first_and_summary_counts_flats_with_dues(world):
    bill(world, OCT, AUG, SEP)  # billed out of order on purpose
    pay(world, world["b"], "3000.00")  # B-1 owes 3 x 1000 -> fully paid

    grid = dues_grid(world["society"])

    assert grid["periods"] == [AUG, SEP, OCT]
    assert grid["summary"] == {"flats": 3, "flats_with_dues": 1, "oldest_unpaid": AUG}


# --- Reversals are netted, never double counted ----------------------------------------------


def test_reversing_a_payment_reopens_the_month_it_had_cleared(world):
    bill(world, AUG)
    payment = pay(world, world["a"], "1500.00")
    assert cells(dues_grid(world["society"]), world["a"])[AUG]["status"] == "paid"

    reverse_entry(society=world["society"], entry=payment, actor=world["people"]["treasurer"])

    c = cells(dues_grid(world["society"]), world["a"])[AUG]
    assert (c["status"], c["billed"], c["due"]) == ("unpaid", D("1500.00"), D("1500.00"))


def test_reversing_a_charge_removes_it_from_its_ORIGINAL_month(world):
    bill(world, AUG, SEP)
    sep_charge = LedgerEntry.objects.get(flat=world["a"], billing_run__period=SEP)

    reverse_entry(society=world["society"], entry=sep_charge, actor=world["people"]["treasurer"])

    c = cells(dues_grid(world["society"]), world["a"])
    assert c[SEP]["status"] == "none"  # cancelled
    assert c[AUG]["status"] == "unpaid"  # untouched


def test_a_charge_outside_billing_is_placed_in_the_month_it_was_created(world):
    record_charge(society=world["society"], flat=world["a"], amount=D("200.00"), note="Repair levy")

    grid = dues_grid(world["society"])

    this_month = date.today().replace(day=1)
    assert grid["periods"] == [this_month]
    assert cells(grid, world["a"])[this_month]["due"] == D("200.00")


# --- The invariant: the grid can never disagree with the ledger ----------------------------


def scenario_plain(w):
    bill(w, AUG, SEP, OCT)
    pay(w, w["a"], "1500.00")


def scenario_partial_across_months(w):
    bill(w, AUG, SEP, OCT)
    pay(w, w["a"], "2250.00")
    pay(w, w["b"], "999.99")


def scenario_payment_reversed(w):
    bill(w, AUG, SEP)
    payment = pay(w, w["a"], "2000.00")
    reverse_entry(society=w["society"], entry=payment, actor=w["people"]["treasurer"])


def scenario_charge_cancelled_then_paid(w):
    bill(w, AUG, SEP, OCT)
    charge = LedgerEntry.objects.get(flat=w["a"], billing_run__period=SEP)
    reverse_entry(society=w["society"], entry=charge, actor=w["people"]["treasurer"])
    pay(w, w["a"], "1500.00")


def scenario_everything(w):
    bill(w, AUG, SEP, OCT)
    first = pay(w, w["a"], "1800.00")
    pay(w, w["a"], "100.50")
    reverse_entry(society=w["society"], entry=first, actor=w["people"]["treasurer"])
    pay(w, w["b"], "2500.00")
    record_charge(society=w["society"], flat=w["b"], amount=D("75.25"))


@pytest.mark.parametrize(
    "scenario",
    [scenario_plain, scenario_partial_across_months, scenario_payment_reversed,
     scenario_charge_cancelled_then_paid, scenario_everything],
)
def test_unpaid_months_always_add_up_to_the_ledger_balance(world, scenario):
    """Proves: the derived grid is consistent with the books, whatever mix of events happened."""
    scenario(world)

    grid = dues_grid(world["society"])

    for flat in (world["a"], world["b"], world["quiet"]):
        shown = row(grid, flat)
        assert shown["outstanding"] == outstanding_for_flat(flat)
        assert sum(c["due"] for c in shown["cells"]) == shown["outstanding"]  # nothing hidden here


def test_old_months_outside_the_window_are_still_paid_first_and_still_counted(world):
    """14 billed months but only 12 shown: the hidden two are paid FIRST and cannot vanish."""
    months = [date(2025, m, 1) for m in range(1, 13)] + [date(2026, 1, 1), date(2026, 2, 1)]
    bill(world, *months)  # B-1 is billed 1000 x 14 = 14000
    pay(world, world["b"], "2500.00")  # clears Jan, Feb and half of Mar 2025 (oldest first)

    grid = dues_grid(world["society"], max_periods=12)

    assert len(grid["periods"]) == 12 and grid["periods"][0] == date(2025, 3, 1)
    shown = row(grid, world["b"])
    assert shown["cells"][0]["status"] == "partial"  # Mar 2025: half paid
    assert shown["outstanding"] == D("11500.00") == outstanding_for_flat(world["b"])


def test_another_societys_money_never_appears(world):
    other = Society.objects.create(name="Lake View", slug="lake-view")
    foreign = Flat.objects.create(society=other, label="X-1", monthly_maintenance=D("9999.00"))
    run_billing(society=other, period=AUG)
    bill(world, SEP)

    grid = dues_grid(world["society"])

    assert grid["periods"] == [SEP]
    assert all(r["label"] != "X-1" for r in grid["flats"])
    assert outstanding_for_flat(foreign) == D("9999.00")


def test_dues_grid_uses_a_constant_number_of_queries(world):
    bill(world, AUG)

    def count():
        with CaptureQueriesContext(connection) as ctx:
            dues_grid(world["society"])
        return len(ctx)

    baseline = count()
    for i in range(6):
        Flat.objects.create(
            society=world["society"], label=f"N-{i}", monthly_maintenance=D("10.00")
        )
    bill(world, SEP, OCT)

    assert count() == baseline == 2


# --- Endpoints --------------------------------------------------------------------------------


def test_dues_endpoint_returns_exact_strings_and_iso_dates(world):
    bill(world, AUG)
    pay(world, world["a"], "500.50")

    body = client_for(world["people"]["treasurer"]).get(
        reverse("dues", kwargs={"society_id": world["society"].id})
    ).json()

    assert body["periods"] == ["2026-08-01"]
    cell = next(r for r in body["flats"] if r["label"] == "A-1")["cells"][0]
    assert cell == {
        "period": "2026-08-01", "billed": "1500.00", "paid": "500.50", "due": "999.50",
        "status": "partial",
    }
    assert body["summary"]["oldest_unpaid"] == "2026-08-01"


@pytest.mark.parametrize("name", ["dues", "billing-runs"])
def test_residents_cannot_read_these_reports(world, name):
    url = reverse(name, kwargs={"society_id": world["society"].id})

    assert client_for(world["people"]["resident"]).get(url).status_code == 403


@pytest.mark.parametrize("name", ["dues", "billing-runs"])
@pytest.mark.parametrize("who", ["admin", "treasurer"])
def test_admin_and_treasurer_can_read_these_reports(world, name, who):
    url = reverse(name, kwargs={"society_id": world["society"].id})

    assert client_for(world["people"][who]).get(url).status_code == 200


# --- Billing run history ----------------------------------------------------------------------


def test_billing_runs_are_listed_newest_month_first_with_exact_totals(world):
    bill(world, AUG, OCT, SEP)

    runs = client_for(world["people"]["admin"]).get(
        reverse("billing-runs", kwargs={"society_id": world["society"].id})
    ).json()

    assert [r["period"] for r in runs] == ["2026-10-01", "2026-09-01", "2026-08-01"]
    assert runs[0]["flats_charged"] == 2 and runs[0]["total_amount"] == "2500.00"


def test_billing_runs_only_list_this_societys_runs(world):
    other = Society.objects.create(name="Lake View", slug="lake-view")
    Flat.objects.create(society=other, label="X-1", monthly_maintenance=D("700.00"))
    run_billing(society=other, period=AUG)

    runs = client_for(world["people"]["admin"]).get(
        reverse("billing-runs", kwargs={"society_id": world["society"].id})
    ).json()

    assert runs == []


# --- recorded_by on ledger entries --------------------------------------------------------


def test_ledger_entries_say_who_recorded_them_without_extra_queries(world):
    bill(world, AUG)
    pay(world, world["a"], "100.00")
    resident = client_for(world["people"]["resident"])
    url = reverse(
        "flat-ledger", kwargs={"society_id": world["society"].id, "flat_id": world["a"].id}
    )

    entries = resident.get(url).json()["entries"]
    who = {e["kind"]: e["recorded_by"] for e in entries}
    assert who == {"charge": "system", "payment": "treasurer"}

    def count():
        with CaptureQueriesContext(connection) as ctx:
            assert resident.get(url).status_code == 200
        return len(ctx)

    baseline = count()
    for _ in range(5):
        pay(world, world["a"], "10.00")
    assert count() == baseline
