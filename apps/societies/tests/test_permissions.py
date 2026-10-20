import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.db import IntegrityError, transaction
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory, force_authenticate
from rest_framework.views import APIView

from apps.societies.models import Flat, Membership, Society
from apps.societies.permissions import HasCapability, IsSocietyMember
from apps.societies.roles import MANAGE_FLATS, ROLE_PERMISSIONS
from apps.societies.services import add_member

pytestmark = pytest.mark.django_db


class ProbeView(APIView):
    """Minimal view that exercises the permission classes without real endpoints."""

    permission_classes = [IsAuthenticated, IsSocietyMember, HasCapability]
    required_capabilities = {"GET": MANAGE_FLATS}

    def get(self, request, society_id):
        return Response({"society": request.society.id, "role": request.membership.role})


def call(user, society_id):
    request = APIRequestFactory().get("/probe/")
    if user is not None:
        force_authenticate(request, user=user)
    return ProbeView.as_view()(request, society_id=society_id)


@pytest.fixture
def green_park():
    return Society.objects.create(name="Green Park", slug="green-park")


@pytest.fixture
def lake_view():
    return Society.objects.create(name="Lake View", slug="lake-view")


def make_user(name):
    return get_user_model().objects.create_user(username=name, password="x")


def test_anonymous_user_is_rejected(green_park):
    assert call(None, green_park.id).status_code in (401, 403)


def test_member_with_capability_gets_200(green_park):
    admin = make_user("admin")
    add_member(society=green_park, user=admin, role="secretary")

    response = call(admin, green_park.id)

    assert response.status_code == 200
    assert response.data == {"society": green_park.id, "role": "secretary"}


def test_member_without_capability_gets_403(green_park):
    flat = Flat.objects.create(society=green_park, label="A-101")
    resident = make_user("resident")
    add_member(society=green_park, user=resident, role="resident", flat=flat)

    assert call(resident, green_park.id).status_code == 403


def test_non_member_gets_404_for_another_tenants_society(green_park, lake_view):
    """CROSS-TENANT: an admin of Lake View cannot touch Green Park, and cannot tell it exists."""
    lake_admin = make_user("lake_admin")
    add_member(society=lake_view, user=lake_admin, role="secretary")

    assert call(lake_admin, green_park.id).status_code == 404


def test_missing_society_looks_identical_to_forbidden_society(green_park):
    user = make_user("someone")
    add_member(society=green_park, user=user, role="secretary")

    unknown = call(user, 999_999)
    assert unknown.status_code == 404
    assert unknown.data == call(make_user("outsider"), green_park.id).data


def test_role_in_one_society_does_not_leak_into_another(green_park, lake_view):
    """A resident in A who is admin in B must NOT get admin powers in A."""
    user = make_user("both")
    flat = Flat.objects.create(society=green_park, label="A-101")
    add_member(society=green_park, user=user, role="resident", flat=flat)
    add_member(society=lake_view, user=user, role="secretary")

    assert call(user, lake_view.id).status_code == 200
    assert call(user, green_park.id).status_code == 403


def test_every_role_has_a_permission_entry():
    assert set(ROLE_PERMISSIONS) == set(Membership.Role.values)


def test_database_rejects_unknown_role(green_park):
    with pytest.raises(IntegrityError), transaction.atomic():
        Membership.objects.create(user=make_user("x"), society=green_park, role="banana")


@pytest.mark.parametrize("role", Membership.Role.values)
def test_every_declared_role_is_accepted_by_the_database(green_park, role):
    """Drift guard: adding a Role without updating the CHECK constraint fails here."""
    flat = Flat.objects.create(society=green_park, label="A-1") if role == "resident" else None
    Membership.objects.create(user=make_user(f"u_{role}"), society=green_park, role=role, flat=flat)



class WrongOrderView(ProbeView):
    permission_classes = [IsAuthenticated, HasCapability, IsSocietyMember]


def test_wrong_permission_order_crashes_loudly_instead_of_defaulting(green_park):
    admin = make_user("admin")
    add_member(society=green_park, user=admin, role="secretary")
    request = APIRequestFactory().get("/probe/")
    force_authenticate(request, user=admin)

    with pytest.raises(ImproperlyConfigured):
        WrongOrderView.as_view()(request, society_id=green_park.id)


def test_http_method_not_listed_in_required_capabilities_is_denied(green_park):
    admin = make_user("admin")
    add_member(society=green_park, user=admin, role="secretary")
    request = APIRequestFactory().post("/probe/")
    force_authenticate(request, user=admin)

    class PostProbe(ProbeView):
        def post(self, request, society_id):
            return Response({})

    assert PostProbe.as_view()(request, society_id=green_park.id).status_code == 403
