import time

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from apps.audit.models import AuditLog
from apps.ledger.tests.helpers import run_in_parallel
from apps.societies import roles
from apps.societies import services as society_services
from apps.societies.models import Flat, Membership, Society
from apps.societies.services import MembershipChangeNotAllowed, add_member, change_member

pytestmark = pytest.mark.django_db


def make_user(name):
    return get_user_model().objects.create_user(username=name, password="x")


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def world():
    society = Society.objects.create(name="Green Park", slug="green-park")
    flats = {n: Flat.objects.create(society=society, label=n) for n in ("A-1", "A-2", "A-3", "A-4")}
    users, members = {}, {}
    for name, role, flat in [
        ("president", "president", "A-1"),
        ("secretary", "secretary", "A-2"),
        ("treasurer", "treasurer", "A-3"),
        ("ravi", "resident", "A-4"),
    ]:
        users[name] = make_user(name)
        members[name] = add_member(
            society=society, user=users[name], role=role, flat=flats[flat]
        )
    return {"society": society, "flats": flats, "users": users, "members": members}


def patch_url(world, member):
    return reverse(
        "member-detail", kwargs={"society_id": world["society"].id, "member_id": member.id}
    )


def change(world, actor, member, body):
    return client_for(world["users"][actor]).patch(patch_url(world, member), body, format="json")


# --- Who may do it ---------------------------------------------------------------------------


@pytest.mark.parametrize("actor", ["president", "secretary"])
def test_president_and_secretary_can_change_a_role(world, actor):
    response = change(world, actor, world["members"]["ravi"], {"role": "treasurer"})

    assert response.status_code == 200
    assert response.json()["role"] == "treasurer"
    world["members"]["ravi"].refresh_from_db()
    assert world["members"]["ravi"].role == "treasurer"


@pytest.mark.parametrize("actor", ["treasurer", "ravi"])
def test_treasurer_and_resident_cannot_change_roles(world, actor):
    response = change(world, actor, world["members"]["president"], {"role": "resident"})

    assert response.status_code == 403
    world["members"]["president"].refresh_from_db()
    assert world["members"]["president"].role == "president"


def test_a_promotion_takes_effect_on_the_very_next_request(world):
    society_id = world["society"].id
    summary = reverse("summary", kwargs={"society_id": society_id})
    ravi = client_for(world["users"]["ravi"])
    assert ravi.get(summary).status_code == 403  # a resident cannot read the society's books

    change(world, "secretary", world["members"]["ravi"], {"role": "treasurer"})

    assert ravi.get(summary).status_code == 200  # no re-login, no cache


def test_a_demotion_takes_effect_on_the_very_next_request(world):
    society_id = world["society"].id
    summary = reverse("summary", kwargs={"society_id": society_id})
    treasurer = client_for(world["users"]["treasurer"])
    assert treasurer.get(summary).status_code == 200

    change(world, "secretary", world["members"]["treasurer"], {"role": "resident"})

    assert treasurer.get(summary).status_code == 403


# --- The loophole this closes -----------------------------------------------------------------


@pytest.mark.parametrize("body", [{"role": "president"}, {"flat": None}, {"role": "resident"}])
def test_nobody_may_change_their_own_role_or_flat(world, body):
    """Otherwise a secretary could clear their own flat, record payments for it, and put it back."""
    response = change(world, "secretary", world["members"]["secretary"], body)

    assert response.status_code == 409
    assert "own role or flat" in response.json()["detail"]
    world["members"]["secretary"].refresh_from_db()
    assert (world["members"]["secretary"].role, world["members"]["secretary"].flat) == (
        "secretary",
        world["flats"]["A-2"],
    )


# --- Role and flat rules ----------------------------------------------------------------------


def test_an_office_bearer_can_be_given_or_stripped_of_a_flat(world):
    outsider = add_member(
        society=world["society"], user=make_user("outsider"), role="treasurer"
    )

    gave = change(world, "president", outsider, {"flat": world["flats"]["A-4"].id})
    cleared = change(world, "president", outsider, {"flat": None})

    assert gave.status_code == 200 and gave.json()["flat"] == world["flats"]["A-4"].id
    assert cleared.status_code == 200 and cleared.json()["flat"] is None


def test_a_resident_cannot_have_their_flat_cleared(world):
    response = change(world, "secretary", world["members"]["ravi"], {"flat": None})

    assert response.status_code == 400 and "flat" in response.json()
    world["members"]["ravi"].refresh_from_db()
    assert world["members"]["ravi"].flat is not None


def test_turning_an_office_bearer_without_a_flat_into_a_resident_needs_one(world):
    outsider = add_member(society=world["society"], user=make_user("outsider"), role="secretary")

    without = change(world, "president", outsider, {"role": "resident"})
    with_flat = change(
        world, "president", outsider, {"role": "resident", "flat": world["flats"]["A-4"].id}
    )

    assert without.status_code == 400 and "flat" in without.json()
    assert with_flat.status_code == 200 and with_flat.json()["role"] == "resident"


def test_a_flat_from_another_society_is_rejected(world):
    other = Society.objects.create(name="Lake View", slug="lake-view")
    foreign = Flat.objects.create(society=other, label="B-1")

    response = change(world, "secretary", world["members"]["ravi"], {"flat": foreign.id})

    assert response.status_code == 400 and "flat" in response.json()


@pytest.mark.parametrize("body", [{}, {"role": "emperor"}])
def test_an_empty_or_unknown_change_is_a_400(world, body):
    assert change(world, "secretary", world["members"]["ravi"], body).status_code == 400


def test_a_change_that_changes_nothing_is_a_quiet_success(world):
    before = AuditLog.objects.count()

    response = change(world, "secretary", world["members"]["ravi"], {"role": "resident"})

    assert response.status_code == 200
    assert AuditLog.objects.count() == before  # nothing happened, so nothing is logged


# --- Audit ---------------------------------------------------------------------------------------


def test_a_change_is_audited_with_before_and_after(world):
    change(
        world, "secretary", world["members"]["ravi"],
        {"role": "treasurer", "flat": world["flats"]["A-3"].id},
    )

    row = AuditLog.objects.get(action="member.updated")
    assert row.actor == world["users"]["secretary"]
    assert row.data == {
        "username": "ravi",
        "from_role": "resident",
        "from_flat": "A-4",
        "to_role": "treasurer",
        "to_flat": "A-3",
    }


# --- Keeping a manager -------------------------------------------------------------------------


def test_the_last_manager_cannot_be_demoted_even_by_a_direct_call(world):
    """Through the API the actor is always a second manager, so this guards direct service use."""
    # Remove the president from management first, leaving the secretary as the only manager.
    Membership.objects.filter(pk=world["members"]["president"].pk).update(role="treasurer")

    with pytest.raises(MembershipChangeNotAllowed, match="at least one president or secretary"):
        change_member(
            society=world["society"],
            actor=world["users"]["ravi"],
            membership=world["members"]["secretary"],
            role="resident",
        )

    world["members"]["secretary"].refresh_from_db()
    assert world["members"]["secretary"].role == "secretary"


@pytest.mark.django_db(transaction=True)
def test_two_managers_demoting_each_other_at_once_leave_one(world, monkeypatch):
    """Proves: the manager rows are locked in a fixed order, so the race cannot empty the role."""
    # Widen the race: pause just before commit, so a missing lock cannot hide behind timing.
    real_record = society_services.audit.record

    def slow_record(**kwargs):
        time.sleep(0.15)
        return real_record(**kwargs)

    monkeypatch.setattr(society_services.audit, "record", slow_record)

    president, secretary = world["members"]["president"], world["members"]["secretary"]

    def act(i):
        actor, target = (
            (world["users"]["president"], secretary) if i == 0
            else (world["users"]["secretary"], president)
        )
        try:
            change_member(
                society=world["society"], actor=actor, membership=target, role="resident",
                flat=target.flat,
            )
            return "demoted"
        except MembershipChangeNotAllowed:
            return "refused"

    results = run_in_parallel(2, act)

    assert sorted(results) == ["demoted", "refused"]
    managers = roles.roles_with(roles.MANAGE_MEMBERS)
    assert Membership.objects.filter(society=world["society"], role__in=managers).count() == 1


# --- The capability table -------------------------------------------------------------------------


def test_every_role_has_exactly_the_capabilities_in_the_design():
    """A drift guard: change the table on purpose or this fails."""
    office = {
        roles.VIEW_FLATS, roles.VIEW_ALL_BALANCES, roles.VIEW_EXPENSES, roles.VIEW_AUDIT,
        roles.VIEW_OWN_DUES, roles.RECORD_PAYMENT, roles.REVERSE_ENTRY,
        roles.VIEW_BILLING_SETTINGS, roles.SUBMIT_CLAIM, roles.RESOLVE_CLAIM,
        roles.SEND_REMINDERS,
    }
    assert roles.ROLE_PERMISSIONS == {
        "president": office | {roles.MANAGE_FLATS, roles.MANAGE_MEMBERS, roles.MANAGE_BILLING},
        "secretary": office | {roles.MANAGE_FLATS, roles.MANAGE_MEMBERS},
        "treasurer": office | {roles.RECORD_EXPENSE},
        "resident": {roles.VIEW_OWN_DUES, roles.SUBMIT_CLAIM},
    }
    assert roles.roles_with(roles.RECORD_EXPENSE) == ["treasurer"]
    assert roles.roles_with(roles.MANAGE_BILLING) == ["president"]  # the president alone decides
    assert roles.roles_with(roles.MANAGE_MEMBERS) == ["president", "secretary"]
