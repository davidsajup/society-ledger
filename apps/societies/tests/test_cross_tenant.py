"""Cross-tenant isolation suite.

Proves: an admin of society A (the strongest role in their own tenant) cannot read, create,
change or delete anything in society B, through ANY route and ANY HTTP method, and cannot tell
whether B's objects exist.

The attacker is deliberately an ADMIN, so a 404 can only come from tenant isolation and never
from a lack of role privileges.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from apps.audit import urls as audit_urls
from apps.audit.models import AuditLog
from apps.expenses import urls as expenses_urls
from apps.expenses.models import Expense
from apps.expenses.services import record_expense
from apps.ledger import urls as ledger_urls
from apps.ledger.models import LedgerEntry
from apps.ledger.services import record_charge
from apps.reports import urls as reports_urls
from apps.societies import urls as societies_urls
from apps.societies.models import Flat, Membership, Society
from apps.societies.services import add_member

pytestmark = pytest.mark.django_db

METHODS = ["get", "post", "put", "patch", "delete"]

# Every route under /api/societies/<society_id>/. The guard test below fails if a route is
# added to societies/urls.py or ledger/urls.py without being listed here.
ROUTES = {
    "flat-list": lambda b: {"society_id": b["society"].id},
    "flat-detail": lambda b: {"society_id": b["society"].id, "pk": b["flat"].id},
    "member-list": lambda b: {"society_id": b["society"].id},
    "payment-create": lambda b: {"society_id": b["society"].id, "flat_id": b["flat"].id},
    "flat-ledger": lambda b: {"society_id": b["society"].id, "flat_id": b["flat"].id},
    "entry-reverse": lambda b: {"society_id": b["society"].id, "entry_id": b["entry"].id},
    "expense-list": lambda b: {"society_id": b["society"].id},
    "expense-reverse": lambda b: {"society_id": b["society"].id, "expense_id": b["expense"].id},
    "audit-list": lambda b: {"society_id": b["society"].id},
    "summary": lambda b: {"society_id": b["society"].id},
    "activity": lambda b: {"society_id": b["society"].id},
    "dues": lambda b: {"society_id": b["society"].id},
    "billing-runs": lambda b: {"society_id": b["society"].id},
    "person-create": lambda b: {"society_id": b["society"].id},
    "member-reissue": lambda b: {"society_id": b["society"].id, "member_id": b["member"].id},
    "member-detail": lambda b: {"society_id": b["society"].id, "member_id": b["member"].id},
}

PAYLOAD = {
    "label": "HACKED",
    "username": "attacker-target",
    "role": "secretary",
    "amount": "10.00",
    "note": "HACKED",
    "category": "other",
    "description": "HACKED",
    "name": "HACKED",
    "paid_on": "2026-10-01",
}


def make_user(name):
    return get_user_model().objects.create_user(username=name, password="x")


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def snapshot(society):
    """Everything tenant B owns, in a comparable form."""
    return {
        "flats": list(Flat.objects.for_society(society).order_by("id").values("id", "label")),
        "members": list(
            Membership.objects.for_society(society)
            .order_by("id")
            .values("id", "user_id", "role", "flat_id")
        ),
        "ledger": list(
            LedgerEntry.objects.for_society(society)
            .order_by("id")
            .values("id", "flat_id", "kind", "amount", "reverses_id")
        ),
        "expenses": list(
            Expense.objects.for_society(society)
            .order_by("id")
            .values("id", "amount", "description", "reverses_id")
        ),
        "audit": list(
            AuditLog.objects.for_society(society).order_by("id").values("id", "action", "object_id")
        ),
    }


@pytest.fixture
def tenant_b():
    society = Society.objects.create(name="Lake View", slug="lake-view")
    flat = Flat.objects.create(society=society, label="B-101")
    admin = make_user("b_admin")
    add_member(society=society, user=admin, role="secretary")
    resident = make_user("b_resident")
    member = add_member(society=society, user=resident, role="resident", flat=flat)
    entry = record_charge(society=society, flat=flat, amount=Decimal("100.00"))
    expense, _ = record_expense(
        society=society, actor=admin, category="repairs", description="Lift motor",
        amount=Decimal("500.00"), paid_on=date(2026, 10, 1),
    )
    return {
        "society": society, "flat": flat, "entry": entry, "expense": expense, "member": member,
        "admin": admin, "resident": resident,
    }


@pytest.fixture(params=["president", "secretary", "treasurer"])
def attacker(request):
    """The strongest roles of society A: full power in their own tenant, no membership in B.

    Admin covers the member/flat routes; treasurer covers the money routes.
    """
    society = Society.objects.create(name="Green Park", slug="green-park")
    user = make_user("a_attacker")
    add_member(society=society, user=user, role=request.param)
    make_user("attacker-target")  # a real user, so a leaked write could actually succeed
    return {"society": society, "client": client_for(user)}


@pytest.mark.parametrize("method", METHODS)
@pytest.mark.parametrize("route", ROUTES)
def test_admin_of_one_society_gets_404_on_every_route_of_another(
    route, method, attacker, tenant_b
):
    before = snapshot(tenant_b["society"])
    url = reverse(route, kwargs=ROUTES[route](tenant_b))

    response = getattr(attacker["client"], method)(url, PAYLOAD)

    assert response.status_code == 404
    assert snapshot(tenant_b["society"]) == before  # nothing was read-then-changed either


@pytest.mark.parametrize("method", ["get", "patch", "put", "delete"])
def test_own_society_url_with_other_societys_object_id_leaks_nothing(method, attacker, tenant_b):
    """IDOR: valid society in the URL, but the object id belongs to tenant B.

    The response must be identical to the one for an id that does not exist anywhere, so the
    attacker cannot learn that B's flat exists. (PUT/DELETE are 403 for both: deny by default.)
    """
    society_id = attacker["society"].id
    foreign = reverse("flat-detail", kwargs={"society_id": society_id, "pk": tenant_b["flat"].id})
    nonexistent = reverse("flat-detail", kwargs={"society_id": society_id, "pk": 999_999})

    on_foreign = getattr(attacker["client"], method)(foreign, {"label": "HACKED"})
    on_nonexistent = getattr(attacker["client"], method)(nonexistent, {"label": "HACKED"})

    assert on_foreign.status_code == on_nonexistent.status_code
    assert on_foreign.status_code in (403, 404)
    assert on_foreign.data == on_nonexistent.data
    tenant_b["flat"].refresh_from_db()
    assert tenant_b["flat"].label == "B-101"


def test_nonexistent_society_is_indistinguishable_from_a_forbidden_one(attacker, tenant_b):
    forbidden = attacker["client"].get(
        reverse("flat-list", kwargs={"society_id": tenant_b["society"].id})
    )
    missing = attacker["client"].get(reverse("flat-list", kwargs={"society_id": 999_999}))

    assert forbidden.status_code == missing.status_code == 404
    assert forbidden.data == missing.data


def test_user_with_no_membership_anywhere_is_locked_out(tenant_b):
    stranger = client_for(make_user("stranger"))

    for route in ROUTES:
        url = reverse(route, kwargs=ROUTES[route](tenant_b))
        assert stranger.get(url).status_code == 404


@pytest.mark.parametrize("method", METHODS)
@pytest.mark.parametrize("route", ROUTES)
def test_the_super_admin_also_gets_404_on_every_society_route(route, method, tenant_b):
    """The platform operator onboards societies but is a member of none, so sees no money.

    Being a superuser must not be a tenant escape hatch: same 404, same untouched data.
    """
    super_admin = get_user_model().objects.create_superuser(username="root", password="x")
    before = snapshot(tenant_b["society"])
    url = reverse(route, kwargs=ROUTES[route](tenant_b))

    response = getattr(client_for(super_admin), method)(url, PAYLOAD)

    assert response.status_code == 404
    assert snapshot(tenant_b["society"]) == before


def test_leaked_response_bodies_never_mention_other_tenants_data(attacker, tenant_b):
    """Even a legitimate list call in A must not contain a single byte of B's data."""
    Flat.objects.create(society=attacker["society"], label="A-1")

    response = attacker["client"].get(
        reverse("flat-list", kwargs={"society_id": attacker["society"].id})
    )

    assert "B-101" not in response.content.decode()
    assert "b_resident" not in attacker["client"].get(
        reverse("member-list", kwargs={"society_id": attacker["society"].id})
    ).content.decode()


# --- Guard: a new route cannot ship without cross-tenant coverage ---------------------------


def test_every_societies_route_is_covered_by_this_suite():
    modules = (societies_urls, ledger_urls, expenses_urls, audit_urls, reports_urls)
    declared = {p.name for module in modules for p in module.urlpatterns}
    assert declared == set(ROUTES), (
        f"Routes without cross-tenant tests: {declared - set(ROUTES)}; "
        f"stale entries: {set(ROUTES) - declared}"
    )
