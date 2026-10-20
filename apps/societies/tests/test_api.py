import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework.test import APIClient

from apps.societies.models import Flat, Membership, Society
from apps.societies.services import add_member

pytestmark = pytest.mark.django_db


def make_user(name):
    return get_user_model().objects.create_user(username=name, password="x")


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def green_park():
    return Society.objects.create(name="Green Park", slug="green-park")


@pytest.fixture
def lake_view():
    return Society.objects.create(name="Lake View", slug="lake-view")


@pytest.fixture
def admin(green_park):
    user = make_user("admin")
    add_member(society=green_park, user=user, role="secretary")
    return client_for(user)


@pytest.fixture
def treasurer(green_park):
    user = make_user("treasurer")
    add_member(society=green_park, user=user, role="treasurer")
    return client_for(user)


@pytest.fixture
def resident(green_park):
    user = make_user("resident")
    flat = Flat.objects.create(society=green_park, label="R-1")
    add_member(society=green_park, user=user, role="resident", flat=flat)
    return client_for(user)


def flats_url(society):
    return reverse("flat-list", kwargs={"society_id": society.id})


def flat_url(society, flat):
    return reverse("flat-detail", kwargs={"society_id": society.id, "pk": flat.id})


def members_url(society):
    return reverse("member-list", kwargs={"society_id": society.id})


# --- Flats ---------------------------------------------------------------------------------


def test_admin_creates_flat_and_it_belongs_to_the_url_society(admin, green_park):
    response = admin.post(flats_url(green_park), {"label": "A-101"})

    assert response.status_code == 201
    assert Flat.objects.get(pk=response.data["id"]).society == green_park


def test_client_cannot_choose_the_tenant_via_request_body(admin, green_park, lake_view):
    response = admin.post(flats_url(green_park), {"label": "A-101", "society": lake_view.id})

    assert response.status_code == 201
    assert Flat.objects.get(pk=response.data["id"]).society == green_park


def test_duplicate_label_in_same_society_is_400_not_500(admin, green_park):
    admin.post(flats_url(green_park), {"label": "A-101"})
    response = admin.post(flats_url(green_park), {"label": "A-101"})

    assert response.status_code == 400


def test_same_label_in_another_society_is_fine(admin, green_park, lake_view):
    Flat.objects.create(society=lake_view, label="A-101")

    assert admin.post(flats_url(green_park), {"label": "A-101"}).status_code == 201


def test_flat_list_only_contains_this_societys_flats(treasurer, green_park, lake_view):
    Flat.objects.create(society=green_park, label="A-1")
    Flat.objects.create(society=lake_view, label="B-1")

    labels = [f["label"] for f in treasurer.get(flats_url(green_park)).data]

    assert labels == ["A-1"]


def test_treasurer_can_read_but_not_create_flats(treasurer, green_park):
    assert treasurer.get(flats_url(green_park)).status_code == 200
    assert treasurer.post(flats_url(green_park), {"label": "X-1"}).status_code == 403


def test_resident_cannot_list_flats(resident, green_park):
    assert resident.get(flats_url(green_park)).status_code == 403


def test_admin_can_rename_flat_but_not_delete_it(admin, green_park):
    flat = Flat.objects.create(society=green_park, label="A-1")

    assert admin.patch(flat_url(green_park, flat), {"label": "A-2"}).status_code == 200
    # Not 405: permissions run first and DELETE is not in required_capabilities (deny by default).
    assert admin.delete(flat_url(green_park, flat)).status_code == 403


def test_admin_cannot_fetch_a_flat_id_from_another_society(admin, green_park, lake_view):
    foreign = Flat.objects.create(society=lake_view, label="B-1")

    # The id is real, but it is not in Green Park's queryset: 404, not 403.
    assert admin.get(flat_url(green_park, foreign)).status_code == 404
    assert admin.patch(flat_url(green_park, foreign), {"label": "hacked"}).status_code == 404
    foreign.refresh_from_db()
    assert foreign.label == "B-1"


# --- Members -------------------------------------------------------------------------------


def test_admin_adds_resident_to_a_flat(admin, green_park):
    make_user("newbie")
    flat = Flat.objects.create(society=green_park, label="A-1")

    response = admin.post(
        members_url(green_park), {"username": "newbie", "role": "resident", "flat": flat.id}
    )

    assert response.status_code == 201
    assert Membership.objects.get(user__username="newbie").society == green_park


def test_cannot_attach_a_member_to_a_flat_from_another_society(admin, green_park, lake_view):
    make_user("newbie")
    foreign = Flat.objects.create(society=lake_view, label="B-1")

    response = admin.post(
        members_url(green_park), {"username": "newbie", "role": "resident", "flat": foreign.id}
    )

    assert response.status_code == 400
    assert not Membership.objects.filter(user__username="newbie").exists()


def test_resident_role_without_flat_is_400(admin, green_park):
    make_user("newbie")

    response = admin.post(members_url(green_park), {"username": "newbie", "role": "resident"})

    assert response.status_code == 400


def test_adding_same_user_twice_is_400(admin, green_park):
    make_user("newbie")
    admin.post(members_url(green_park), {"username": "newbie", "role": "treasurer"})

    response = admin.post(members_url(green_park), {"username": "newbie", "role": "secretary"})

    # The message must be keyed to the field the UI shows it on. A bare list of messages (the
    # old behaviour) was refused by the server but displayed nothing to the user.
    assert response.status_code == 400
    assert response.json() == {"username": ["This person is already a member of this society."]}
    assert Membership.objects.filter(user__username="newbie").count() == 1


def test_a_concurrent_duplicate_caught_by_the_database_is_still_a_readable_400(
    admin, green_park, monkeypatch
):
    """Two admins add the same person at the same instant: the DB constraint rejects the loser."""
    make_user("newbie")

    def lose_the_race(**kwargs):
        raise IntegrityError("duplicate key value violates unique constraint")

    monkeypatch.setattr("apps.societies.serializers.add_member", lose_the_race)

    response = admin.post(members_url(green_park), {"username": "newbie", "role": "secretary"})

    assert response.status_code == 400
    assert "already a member" in response.json()["username"][0]


def test_every_member_error_is_keyed_to_a_field_the_ui_can_show(admin, green_park):
    make_user("newbie")
    other = Society.objects.create(name="Lake View", slug="lake-view")
    foreign_flat = Flat.objects.create(society=other, label="B-1")

    unknown = admin.post(members_url(green_park), {"username": "ghost", "role": "secretary"})
    foreign = admin.post(
        members_url(green_park), {"username": "newbie", "role": "resident", "flat": foreign_flat.id}
    )
    resident_without_flat = admin.post(
        members_url(green_park), {"username": "newbie", "role": "resident"}
    )

    assert "username" in unknown.json()
    assert foreign.status_code == 400 and "flat" in foreign.json()
    assert not Membership.objects.filter(user__username="newbie").exists()
    assert resident_without_flat.status_code == 400
    assert all(isinstance(value, (list, str)) for value in resident_without_flat.json().values())


def test_unknown_username_is_400(admin, green_park):
    response = admin.post(members_url(green_park), {"username": "ghost", "role": "secretary"})

    assert response.status_code == 400


def test_only_admin_can_manage_members(treasurer, resident, green_park):
    assert treasurer.get(members_url(green_park)).status_code == 403
    assert resident.get(members_url(green_park)).status_code == 403


def test_member_list_runs_a_constant_number_of_queries(admin, green_park):
    """N+1 guard: query count must not grow with the number of members."""

    def count_queries():
        with CaptureQueriesContext(connection) as ctx:
            assert admin.get(members_url(green_park)).status_code == 200
        return len(ctx)

    baseline = count_queries()
    for i in range(5):
        flat = Flat.objects.create(society=green_park, label=f"N-{i}")
        add_member(society=green_park, user=make_user(f"n{i}"), role="resident", flat=flat)

    assert count_queries() == baseline


# --- Monthly maintenance amount (used by the billing job) -----------------------------------


def test_admin_sets_monthly_maintenance_and_it_is_an_exact_string(admin, green_park):
    flat = Flat.objects.create(society=green_park, label="A-1")

    response = admin.patch(flat_url(green_park, flat), {"monthly_maintenance": "1500.50"})

    assert response.status_code == 200
    assert response.json()["monthly_maintenance"] == "1500.50"
    flat.refresh_from_db()
    assert str(flat.monthly_maintenance) == "1500.50"


@pytest.mark.parametrize("bad", ["-1", "10.001", "abc"])
def test_bad_monthly_maintenance_is_400(admin, green_park, bad):
    flat = Flat.objects.create(society=green_park, label="A-1")

    response = admin.patch(flat_url(green_park, flat), {"monthly_maintenance": bad})

    assert response.status_code == 400


def test_treasurer_cannot_change_monthly_maintenance(treasurer, green_park):
    flat = Flat.objects.create(society=green_park, label="A-1")

    response = treasurer.patch(flat_url(green_park, flat), {"monthly_maintenance": "9.00"})

    assert response.status_code == 403
