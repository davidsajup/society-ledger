"""The super admin: onboards societies, sees no money, and nobody else can use the platform API.

What these tests prove
* Only a settled super admin reaches /api/platform/. Every society role, a staff user who is not a
  superuser, an anonymous caller and a super admin on a temporary password are all refused.
* Creating a society is atomic: society + president login + audit rows, or nothing.
* The temporary password appears in the one creation response and nowhere else.
* The list gives counts and logins, never money.
* The super admin's own isolation (404 on every society route) is proven in
  apps/societies/tests/test_cross_tenant.py.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.credentials import login_status
from apps.audit.models import AuditLog
from apps.ledger.services import record_charge
from apps.onboarding import urls as onboarding_urls
from apps.societies import services
from apps.societies.models import Flat, Membership, Society
from apps.societies.services import (
    NotPlatformAdmin,
    add_member,
    create_member_login,
    create_society,
)

pytestmark = pytest.mark.django_db

User = get_user_model()

# Automatic billing may begin at the start of next year: always in the future, a cycle start.
BILLING_START = date(date.today().year + 1, 1, 1)
NEW_SOCIETY = {
    "name": "Green Meadows",
    "slug": "green-meadows",
    "president_name": "Vikram Rao",
    "billing_cycle_months": 3,
    "billing_start": BILLING_START,
}

# Every platform route. The guard test fails if a route is added without being listed here.
ROUTES = {
    "platform-society-list": lambda: {},
    "platform-manager-reissue": lambda: {"society_id": 1, "member_id": 1},
}


def client_for(user=None):
    client = APIClient()
    if user is not None:
        client.force_authenticate(user=user)
    return client


@pytest.fixture
def super_admin():
    return User.objects.create_superuser(username="root", password="x")


@pytest.fixture
def onboarded(super_admin):
    """A society created through the real service, plus its president's one-time password."""
    society, membership, password = create_society(actor=super_admin, **NEW_SOCIETY)
    return {"society": society, "president": membership, "password": password}


def society_user(role, name):
    society = Society.objects.create(name=f"{name} society", slug=f"{name}-society")
    user = User.objects.create_user(username=name, password="x")
    flat = Flat.objects.create(society=society, label="A-1")
    add_member(society=society, user=user, role=role, flat=flat if role == "resident" else None)
    return user


# --- Who can reach the platform API --------------------------------------------------------


@pytest.mark.parametrize("method", ["get", "post"])
@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("role", ["president", "secretary", "treasurer", "resident"])
def test_every_society_role_is_refused(role, route, method):
    user = society_user(role, f"u-{role}")
    before = Society.objects.count()

    response = getattr(client_for(user), method)(
        reverse(route, kwargs=ROUTES[route]()), NEW_SOCIETY
    )

    assert response.status_code == 403
    assert Society.objects.count() == before


@pytest.mark.parametrize("method", ["get", "post"])
@pytest.mark.parametrize("route", ROUTES)
def test_anonymous_and_non_superuser_staff_are_refused(route, method):
    staff = User.objects.create_user(username="staff", password="x", is_staff=True)
    url = reverse(route, kwargs=ROUTES[route]())

    assert getattr(client_for(), method)(url, NEW_SOCIETY).status_code == 403
    assert getattr(client_for(staff), method)(url, NEW_SOCIETY).status_code == 403
    assert Society.objects.count() == 0


def test_a_super_admin_on_a_temporary_password_must_change_it_first(super_admin):
    super_admin.must_change_password = True
    super_admin.save()

    response = client_for(super_admin).post(reverse("platform-society-list"), NEW_SOCIETY)

    assert response.status_code == 403
    assert response.data["code"] == "password_change_required"
    assert Society.objects.count() == 0


# --- Creating a society --------------------------------------------------------------------


def test_creating_a_society_makes_the_society_and_a_president_login(super_admin):
    response = client_for(super_admin).post(reverse("platform-society-list"), NEW_SOCIETY)

    assert response.status_code == 201
    assert response["Cache-Control"] == "no-store"
    society = Society.objects.get(slug="green-meadows")
    president = Membership.objects.for_society(society).get()
    assert president.role == "president"
    assert president.flat is None  # the society has no flats yet; the president adds them
    assert president.user.username == response.data["username"]
    assert president.user.first_name == "Vikram Rao"
    assert response.data["society"]["id"] == society.id
    # A random one-time password that must be replaced at first login.
    assert len(response.data["temp_password"]) >= 10
    assert president.user.check_password(response.data["temp_password"])
    assert president.user.must_change_password is True
    assert login_status(president.user) == "temporary"


def test_the_president_must_change_the_password_before_using_the_society(onboarded):
    president_client = client_for(onboarded["president"].user)

    response = president_client.get(
        reverse("flat-list", kwargs={"society_id": onboarded["society"].id})
    )

    assert response.status_code == 403
    assert response.data["code"] == "password_change_required"


def test_creation_is_audited_with_the_super_admin_as_actor(super_admin, onboarded):
    rows = AuditLog.objects.for_society(onboarded["society"]).order_by("id")

    assert [r.action for r in rows] == ["society.created", "member.created"]
    assert all(r.actor_id == super_admin.id for r in rows)


def test_the_password_is_never_stored_or_returned_again(super_admin, onboarded):
    password = onboarded["password"]

    audit = str(list(AuditLog.objects.values_list("data", flat=True)))
    listing = client_for(super_admin).get(reverse("platform-society-list")).content.decode()

    assert password not in audit
    assert password not in listing
    assert password not in onboarded["president"].user.password  # only a hash is stored


@pytest.mark.parametrize(
    "payload, field",
    [
        ({**NEW_SOCIETY, "name": "   "}, "name"),
        ({**NEW_SOCIETY, "slug": "Not A Slug!"}, "slug"),
        ({**NEW_SOCIETY, "president_name": ""}, "president_name"),
        ({"name": "x"}, "slug"),
    ],
)
def test_bad_input_is_a_400_keyed_to_the_field_and_creates_nothing(super_admin, payload, field):
    response = client_for(super_admin).post(reverse("platform-society-list"), payload)

    assert response.status_code == 400
    assert field in response.data
    assert Society.objects.count() == 0
    assert User.objects.filter(is_superuser=False).count() == 0


def test_a_duplicate_slug_is_refused_and_leaves_the_first_society_alone(super_admin, onboarded):
    before = (Society.objects.count(), User.objects.count(), AuditLog.objects.count())

    response = client_for(super_admin).post(reverse("platform-society-list"), NEW_SOCIETY)

    assert response.status_code == 400
    assert "slug" in response.data
    assert (Society.objects.count(), User.objects.count(), AuditLog.objects.count()) == before


def test_if_the_president_login_fails_no_empty_society_is_left_behind(super_admin, monkeypatch):
    def boom(**kwargs):
        raise RuntimeError("simulated failure after the society row was written")

    monkeypatch.setattr(services, "create_member_login", boom)

    with pytest.raises(RuntimeError):
        create_society(actor=super_admin, **NEW_SOCIETY)

    assert Society.objects.count() == 0
    assert AuditLog.objects.count() == 0


def test_the_service_refuses_anyone_who_is_not_an_active_super_admin():
    president = society_user("president", "pres")
    inactive = User.objects.create_superuser(username="old", password="x")
    inactive.is_active = False

    for actor in (president, inactive):
        with pytest.raises(NotPlatformAdmin):
            create_society(actor=actor, **NEW_SOCIETY)

    assert Society.objects.filter(slug="green-meadows").count() == 0


# --- Listing: counts and logins, never money -----------------------------------------------


def test_the_list_shows_counts_and_logins_but_no_money(super_admin, onboarded):
    society = onboarded["society"]
    flat = Flat.objects.create(society=society, label="A-1", maintenance_amount=Decimal("1500"))
    record_charge(society=society, flat=flat, amount=Decimal("1500.00"))
    add_member(
        society=society,
        user=User.objects.create_user(username="r", password="x"),
        role="resident",
        flat=flat,
    )

    response = client_for(super_admin).get(reverse("platform-society-list"))

    assert response.status_code == 200
    (row,) = response.data
    assert row["flat_count"] == 1
    assert row["member_count"] == 2
    assert [m["role"] for m in row["managers"]] == ["president"]  # residents are not listed
    assert row["managers"][0]["login_status"] == "temporary"
    text = response.content.decode().lower()
    for money_word in ("amount", "balance", "outstanding", "billed", "collected", "1500"):
        assert money_word not in text


def test_the_list_does_not_run_a_query_per_society(super_admin, django_assert_max_num_queries):
    for n in range(8):
        create_society(
            actor=super_admin, name=f"Society {n}", slug=f"society-{n}", president_name=f"P {n}"
        )

    with django_assert_max_num_queries(8):  # session, user, societies, managers: not 8 x anything
        response = client_for(super_admin).get(reverse("platform-society-list"))

    assert len(response.data) == 8


# --- Reissuing a lost first login ----------------------------------------------------------


def test_reissue_gives_the_president_a_new_password_and_ends_the_old_one(super_admin, onboarded):
    member = onboarded["president"]
    url = reverse(
        "platform-manager-reissue",
        kwargs={"society_id": onboarded["society"].id, "member_id": member.id},
    )

    response = client_for(super_admin).post(url)

    assert response.status_code == 200
    assert response["Cache-Control"] == "no-store"
    member.user.refresh_from_db()
    assert member.user.check_password(response.data["temp_password"])
    assert not member.user.check_password(onboarded["password"])
    row = AuditLog.objects.filter(action="credentials.reissued").get()
    assert row.actor_id == super_admin.id
    assert response.data["temp_password"] not in str(row.data)


def test_reissue_is_only_for_president_or_secretary(super_admin, onboarded):
    society = onboarded["society"]
    treasurer, _ = create_member_login(
        society=society,
        actor=super_admin,
        name="Ravi",
        role="treasurer",
    )
    url = reverse(
        "platform-manager-reissue",
        kwargs={"society_id": society.id, "member_id": treasurer.id},
    )

    response = client_for(super_admin).post(url)

    assert response.status_code == 409
    assert AuditLog.objects.filter(action="credentials.reissued").count() == 0


def test_reissue_refuses_a_person_who_also_belongs_to_another_society(super_admin, onboarded):
    other = Society.objects.create(name="Other", slug="other")
    add_member(society=other, user=onboarded["president"].user, role="resident",
               flat=Flat.objects.create(society=other, label="Z-1"))
    url = reverse(
        "platform-manager-reissue",
        kwargs={"society_id": onboarded["society"].id, "member_id": onboarded["president"].id},
    )

    response = client_for(super_admin).post(url)

    assert response.status_code == 409


def test_reissue_with_a_member_of_another_society_is_a_404(super_admin, onboarded):
    other_society, other_president, _ = create_society(
        actor=super_admin, name="Lake View", slug="lake-view", president_name="Anil Shah"
    )
    url = reverse(
        "platform-manager-reissue",
        kwargs={"society_id": onboarded["society"].id, "member_id": other_president.id},
    )

    assert client_for(super_admin).post(url).status_code == 404


# --- Who the front end treats as a super admin ---------------------------------------------


def test_me_tells_the_front_end_who_the_super_admin_is(super_admin, onboarded):
    admin_me = client_for(super_admin).get(reverse("auth-me")).data
    president_me = client_for(onboarded["president"].user).get(reverse("auth-me")).data

    assert admin_me["is_platform_admin"] is True
    assert admin_me["memberships"] == []
    assert president_me["is_platform_admin"] is False


# --- Guard: a new platform route cannot ship without coverage ------------------------------


def test_every_platform_route_is_covered_by_this_suite():
    declared = {p.name for p in onboarding_urls.urlpatterns}
    assert declared == set(ROUTES), (
        f"Platform routes without tests: {declared - set(ROUTES)}; "
        f"stale entries: {set(ROUTES) - declared}"
    )
