"""The president decides how often the society is billed and when billing starts.

What these tests prove
* Only the president can change it; the secretary and treasurer can read it; a resident cannot.
* It can change only until the first billing run exists; after that it is locked.
* A start date must be the first day of a cycle and not in the past; changing the cycle needs
  the president to confirm they have checked every flat's amount (the same number would mean
  three times the money).
* The daily job and a settings change take the same lock, and the job re-reads the schedule
  after taking it: a run can never exist that the saved schedule forbids.
"""

import time
from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.urls import reverse
from rest_framework.test import APIClient

from apps.audit.models import AuditLog
from apps.billing import services
from apps.billing.models import BillingRun
from apps.billing.services import (
    BillingAlreadyStarted,
    change_billing_settings,
    run_billing,
)
from apps.ledger.models import LedgerEntry
from apps.ledger.tests.helpers import run_in_parallel
from apps.societies.models import Flat, Society
from apps.societies.services import add_member

pytestmark = pytest.mark.django_db
D = Decimal

JAN = date(2027, 1, 1)
APR = date(2027, 4, 1)


@pytest.fixture(autouse=True)
def today(monkeypatch):
    """Fix 'today', so 'not in the past' does not start failing when the real calendar moves on."""
    monkeypatch.setattr(services.timezone, "localdate", lambda: date(2026, 10, 24))


@pytest.fixture
def world():
    society = Society.objects.create(
        name="Varma Heights", slug="varma", billing_cycle_months=3, billing_start=JAN
    )
    flat = Flat.objects.create(society=society, label="A-1", maintenance_amount=D("4500.00"))
    users = {}
    for name, role in [
        ("president", "president"),
        ("secretary", "secretary"),
        ("treasurer", "treasurer"),
        ("resident", "resident"),
    ]:
        user = get_user_model().objects.create_user(username=name, password="x")
        add_member(
            society=society, user=user, role=role, flat=flat if role == "resident" else None
        )
        client = APIClient()
        client.force_authenticate(user=user)
        users[name] = (user, client)
    return {"society": society, "flat": flat, "users": users}


def president(world):
    return world["users"]["president"][0]


def url(world):
    return reverse("billing-settings", kwargs={"society_id": world["society"].id})


def put(world, who, **body):
    payload = {"billing_cycle_months": 3, "billing_start": "2027-01-01", **body}
    return world["users"][who][1].put(url(world), payload, format="json")


# --- Who may read and who may change ---------------------------------------------------------


@pytest.mark.parametrize(
    "who, can_read, can_change",
    [
        ("president", True, True),
        ("secretary", True, False),
        ("treasurer", True, False),
        ("resident", False, False),
    ],
)
def test_who_can_read_and_who_can_change(world, who, can_read, can_change):
    client = world["users"][who][1]

    read = client.get(url(world))
    change = put(world, who, billing_start="2027-04-01")

    assert (read.status_code == 200) is can_read
    assert (change.status_code == 200) is can_change
    if not can_read:
        assert read.status_code == 403
    if not can_change:
        world["society"].refresh_from_db()
        assert world["society"].billing_start == JAN  # nothing was saved


def test_reading_shows_the_schedule_and_whether_it_is_locked(world):
    body = world["users"]["treasurer"][1].get(url(world)).json()

    assert body == {
        "billing_cycle_months": 3,
        "billing_start": "2027-01-01",
        "locked": False,
        "flats_with_amounts": 1,
    }


# --- Changing it -----------------------------------------------------------------------------


def test_the_president_can_move_the_start_date_and_it_is_audited(world):
    response = put(world, "president", billing_start="2027-04-01")

    assert response.status_code == 200
    assert response.json()["billing_start"] == "2027-04-01"
    world["society"].refresh_from_db()
    assert world["society"].billing_start == APR
    audit = AuditLog.objects.get(action="billing.settings_changed")
    assert audit.actor == president(world)
    assert audit.data == {
        "from_cycle_months": 3,
        "from_start": "2027-01-01",
        "to_cycle_months": 3,
        "to_start": "2027-04-01",
        "amounts_reviewed": False,
    }


def test_saving_the_same_schedule_changes_nothing_and_writes_no_audit_row(world):
    _, changed = change_billing_settings(
        society=world["society"], actor=president(world), cycle_months=3, start=JAN
    )

    assert changed is False
    assert AuditLog.objects.filter(action="billing.settings_changed").count() == 0


def test_changing_the_cycle_needs_the_amounts_to_be_confirmed_as_checked(world):
    refused = put(world, "president", billing_cycle_months=1)

    assert refused.status_code == 400
    assert "amounts_reviewed" in refused.json()
    world["society"].refresh_from_db()
    assert world["society"].billing_cycle_months == 3  # unchanged

    accepted = put(world, "president", billing_cycle_months=1, amounts_reviewed=True)

    assert accepted.status_code == 200
    world["society"].refresh_from_db()
    assert world["society"].billing_cycle_months == 1
    audit = AuditLog.objects.get(action="billing.settings_changed")
    assert audit.data["amounts_reviewed"] is True


def test_changing_only_the_date_does_not_ask_about_amounts(world):
    assert put(world, "president", billing_start="2027-04-01").status_code == 200


def test_changing_the_cycle_with_no_amounts_set_needs_no_confirmation(world):
    Flat.objects.update(maintenance_amount=D("0.00"))

    assert put(world, "president", billing_cycle_months=1).status_code == 200


@pytest.mark.parametrize(
    "body, field",
    [
        ({"billing_start": "2027-02-01"}, "billing_start"),  # not a quarter start
        ({"billing_start": "2027-01-15"}, "billing_start"),  # not the first of a month
        ({"billing_start": "2026-07-01"}, "billing_start"),  # in the past
        ({"billing_cycle_months": 2}, "billing_cycle_months"),
        ({"billing_start": None}, "billing_start"),
    ],
)
def test_a_schedule_we_cannot_run_is_refused_with_the_field_named(world, body, field):
    response = put(world, "president", **body)

    assert response.status_code == 400
    assert field in response.json()
    world["society"].refresh_from_db()
    assert (world["society"].billing_cycle_months, world["society"].billing_start) == (3, JAN)


def test_both_fields_are_required(world):
    client = world["users"]["president"][1]

    assert client.put(url(world), {"billing_start": "2027-01-01"}, format="json").status_code == 400
    assert client.put(url(world), {"billing_cycle_months": 3}, format="json").status_code == 400


def test_a_monthly_society_can_start_in_any_month(world):
    assert put(world, "president", billing_cycle_months=1, billing_start="2027-02-01",
               amounts_reviewed=True).status_code == 200


# --- The lock after billing starts ------------------------------------------------------------


def test_after_the_first_billing_run_nothing_can_be_changed(world):
    run_billing(society=world["society"], period=JAN)

    response = put(world, "president", billing_start="2027-04-01")

    assert response.status_code == 409
    world["society"].refresh_from_db()
    assert world["society"].billing_start == JAN
    assert AuditLog.objects.filter(action="billing.settings_changed").count() == 0
    assert world["users"]["treasurer"][1].get(url(world)).json()["locked"] is True


def test_the_service_refuses_after_billing_too_not_only_the_screen(world):
    run_billing(society=world["society"], period=JAN)

    with pytest.raises(BillingAlreadyStarted):
        change_billing_settings(
            society=world["society"], actor=president(world), cycle_months=3, start=APR
        )


# --- The daily job and a settings change -------------------------------------------------------


def test_billing_re_reads_the_schedule_so_a_stale_society_object_cannot_bill_early(world):
    stale = Society.objects.get(pk=world["society"].pk)  # still says "starts in January"
    change_billing_settings(
        society=world["society"], actor=president(world), cycle_months=3, start=APR
    )

    with pytest.raises(ValidationError) as exc:
        run_billing(society=stale, period=JAN)

    assert "starts on 01 April 2027" in exc.value.messages[0]
    assert BillingRun.objects.count() == 0
    assert LedgerEntry.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_a_settings_change_and_the_first_billing_run_never_both_succeed(world, monkeypatch):
    """The president saves a later start date at the very moment the daily job bills January.

    Proves: both take the society row lock. Whichever goes first wins and the other is refused,
    so a billing run can never exist for a cycle the saved schedule says is not yet due.
    Without the lock both pass their checks, the run is created, and the start date moves to
    April anyway: January billed under an April start.
    """
    real = services.billing_has_started

    def slow(society):  # widen the window between "no run yet" and saving the new schedule
        answer = real(society)
        time.sleep(0.3)
        return answer

    monkeypatch.setattr(services, "billing_has_started", slow)
    stale = Society.objects.get(pk=world["society"].pk)
    who = president(world)

    def attempt(i):
        try:
            if i == 0:
                change_billing_settings(society=stale, actor=who, cycle_months=3, start=APR)
            else:
                run_billing(society=stale, period=JAN)
            return "ok"
        except (ValidationError, BillingAlreadyStarted):
            return "refused"

    results = run_in_parallel(2, attempt)

    assert sorted(results) == ["ok", "refused"]
    world["society"].refresh_from_db()
    january_billed = BillingRun.objects.filter(period=JAN).exists()
    assert not (january_billed and world["society"].billing_start == APR)
