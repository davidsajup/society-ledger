import re
from datetime import timedelta

import pytest
from django.contrib.auth import authenticate, get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts import credentials
from apps.accounts.credentials import generate_temp_password, make_username
from apps.audit.models import AuditLog
from apps.societies import services as society_services
from apps.societies.models import Flat, Membership, Society
from apps.societies.services import add_member

pytestmark = pytest.mark.django_db

User = get_user_model()
SOCIETY_PASSWORD = "A-fresh-Passphrase-77"  # a strong password chosen by a person


def make_user(name, password="pw-not-used-123", **extra):
    return User.objects.create_user(username=name, password=password, **extra)


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def world():
    society = Society.objects.create(name="Sunrise Heights", slug="sunrise-heights")
    flat = Flat.objects.create(society=society, label="A-101")
    people = {}
    for name, role, own in [("asha", "admin", None), ("tara", "treasurer", None)]:
        people[name] = make_user(name)
        add_member(society=society, user=people[name], role=role, flat=own)
    return {"society": society, "flat": flat, "people": people, "admin": client_for(people["asha"])}


def people_url(world):
    return reverse("person-create", kwargs={"society_id": world["society"].id})


def members_url(world):
    return reverse("member-list", kwargs={"society_id": world["society"].id})


def reissue_url(world, member_id):
    return reverse(
        "member-reissue", kwargs={"society_id": world["society"].id, "member_id": member_id}
    )


def create_login(world, name="Ravi Kumar", role="resident", flat=True, client=None):
    body = {"name": name, "role": role}
    if flat:
        body["flat"] = world["flat"].id
    return (client or world["admin"]).post(people_url(world), body, format="json")


def login(username, password, client=None):
    return (client or APIClient()).post(
        reverse("auth-login"), {"username": username, "password": password}, format="json"
    )


# --- The password itself ------------------------------------------------------------------


def test_temporary_passwords_are_random_readable_and_never_repeat():
    passwords = {generate_temp_password() for _ in range(2000)}

    assert len(passwords) == 2000
    for p in list(passwords)[:200]:
        assert re.fullmatch(r"[a-z2-9]{4}-[a-z2-9]{4}-[a-z2-9]{4}", p)
        assert not set(p) & set("01oli")  # no look-alike characters on a printed slip


def test_the_password_is_not_derivable_from_the_flat_or_the_name(world):
    response = create_login(world, name="Ravi Kumar")
    user = User.objects.get(username=response.json()["username"])

    guesses = ["A-101", "a101", "a-101", "ravi", "Ravi", "ravi.a-101", "sunrise-heights"]
    for guess in guesses:
        assert authenticate(username=user.username, password=guess) is None
    assert response.json()["temp_password"] not in (user.username, user.first_name)


def test_usernames_are_readable_unique_and_keep_societies_apart(world):
    other = Society.objects.create(name="Lake View", slug="lake-view")
    other_flat = Flat.objects.create(society=other, label="A-101")

    mine = make_username(world["society"], "Ravi Kumar", "A-101", "resident")
    theirs = make_username(other, "Ravi Kumar", other_flat.label, "resident")

    assert mine == "ravi.a-101@sunrise-heights"
    assert theirs == "ravi.a-101@lake-view" and mine != theirs


def test_two_people_with_the_same_name_and_flat_get_different_usernames(world):
    first = create_login(world, name="Ravi Kumar").json()["username"]
    second = create_login(world, name="Ravi Singh").json()["username"]

    assert first != second and User.objects.filter(username__in=[first, second]).count() == 2


# --- Creating a login ---------------------------------------------------------------------


def test_admin_creates_a_login_and_gets_the_one_time_password(world):
    response = create_login(world)

    assert response.status_code == 201
    body = response.json()
    assert body["username"] == "ravi.a-101@sunrise-heights"
    assert re.fullmatch(r"[a-z2-9]{4}(-[a-z2-9]{4}){2}", body["temp_password"])
    assert body["member"]["role"] == "resident" and body["member"]["name"] == "Ravi Kumar"
    assert body["member"]["login_status"] == "temporary"
    expires = timezone.datetime.fromisoformat(body["expires_at"].replace("Z", "+00:00"))
    assert timedelta(days=6, hours=23) < expires - timezone.now() <= timedelta(days=7)
    assert response["Cache-Control"] == "no-store"


def test_the_password_is_stored_only_as_a_hash_and_appears_nowhere_else(world):
    body = create_login(world).json()
    secret = body["temp_password"]
    user = User.objects.get(username=body["username"])

    assert user.password != secret and secret not in user.password
    assert user.must_change_password is True
    audit_text = " ".join(str(row.data) for row in AuditLog.objects.all())
    assert secret not in audit_text
    assert secret not in world["admin"].get(members_url(world)).content.decode()


def test_creating_a_login_is_audited_without_the_password(world):
    body = create_login(world).json()

    row = AuditLog.objects.get(action="member.created")
    assert row.actor == world["people"]["asha"]
    assert row.data == {"username": body["username"], "role": "resident"}


@pytest.mark.parametrize("who", ["tara"])
def test_only_an_admin_can_create_logins(world, who):
    response = create_login(world, client=client_for(world["people"][who]))

    assert response.status_code == 403
    assert not User.objects.filter(username__startswith="ravi").exists()


def test_a_resident_login_needs_a_flat_and_a_non_resident_must_not_have_one(world):
    no_flat = create_login(world, flat=False)
    admin_with_flat = create_login(world, role="admin", flat=True)

    assert no_flat.status_code == 400 and "flat" in no_flat.json()
    assert admin_with_flat.status_code == 400 and "flat" in admin_with_flat.json()
    assert not User.objects.filter(username__startswith="ravi").exists()


def test_a_flat_from_another_society_is_rejected(world):
    other = Society.objects.create(name="Lake View", slug="lake-view")
    foreign = Flat.objects.create(society=other, label="B-1")

    response = world["admin"].post(
        people_url(world), {"name": "Ravi", "role": "resident", "flat": foreign.id}, format="json"
    )

    assert response.status_code == 400
    assert not User.objects.filter(username__startswith="ravi").exists()


def test_a_blank_name_is_rejected(world):
    assert create_login(world, name="   ").status_code == 400


def test_if_the_audit_write_fails_no_account_is_left_behind(world, monkeypatch):
    def broken(**kwargs):
        raise RuntimeError("audit down")

    monkeypatch.setattr(society_services.audit, "record", broken)

    with pytest.raises(RuntimeError):
        create_login(world)

    assert not User.objects.filter(username__startswith="ravi").exists()
    assert Membership.objects.count() == 2  # only the two fixture members


# --- Forced change at first login -------------------------------------------------------


def first_login(world):
    body = create_login(world).json()
    client = APIClient()
    response = login(body["username"], body["temp_password"], client)
    return body, client, response


def test_a_temporary_login_works_but_is_flagged_as_must_change(world):
    _, client, response = first_login(world)

    assert response.status_code == 200
    assert response.json()["must_change_password"] is True
    assert client.get(reverse("auth-me")).json()["must_change_password"] is True


@pytest.mark.parametrize(
    "route", ["flat-list", "member-list", "summary", "dues", "expense-list", "audit-list"]
)
def test_every_society_endpoint_refuses_a_user_on_a_temporary_password(world, route):
    """Proves the rule is enforced by the server, so skipping the change screen gains nothing."""
    user = make_user("temp-admin")
    add_member(society=world["society"], user=user, role="admin")
    User.objects.filter(pk=user.pk).update(must_change_password=True)
    user.refresh_from_db()

    response = client_for(user).get(reverse(route, kwargs={"society_id": world["society"].id}))

    assert response.status_code == 403
    assert response.json()["code"] == "password_change_required"


def test_a_resident_on_a_temporary_password_cannot_read_their_ledger(world):
    body, client, _ = first_login(world)
    member = Membership.objects.get(user__username=body["username"])

    url = reverse(
        "flat-ledger", kwargs={"society_id": world["society"].id, "flat_id": member.flat_id}
    )
    response = client.get(url)

    assert response.status_code == 403 and response.json()["code"] == "password_change_required"


def test_me_logout_and_change_password_stay_reachable(world):
    body, client, _ = first_login(world)

    assert client.get(reverse("auth-me")).status_code == 200
    assert client.post(reverse("auth-logout")).status_code == 204


def test_changing_the_password_unlocks_the_app_and_keeps_the_session(world):
    body, client, _ = first_login(world)
    member = Membership.objects.get(user__username=body["username"])

    changed = client.post(
        reverse("auth-change-password"),
        {"current_password": body["temp_password"], "new_password": SOCIETY_PASSWORD},
        format="json",
    )

    assert changed.status_code == 200 and changed.json()["must_change_password"] is False
    ledger = reverse(
        "flat-ledger", kwargs={"society_id": world["society"].id, "flat_id": member.flat_id}
    )
    assert client.get(ledger).status_code == 200  # same session, no re-login needed
    user = User.objects.get(username=body["username"])
    assert user.must_change_password is False and user.temp_password_expires_at is None
    assert credentials.login_status(user) == "active"


# --- Change password -----------------------------------------------------------------------


def test_the_old_password_stops_working_and_the_new_one_works(world):
    body, client, _ = first_login(world)
    client.post(
        reverse("auth-change-password"),
        {"current_password": body["temp_password"], "new_password": SOCIETY_PASSWORD},
        format="json",
    )

    assert login(body["username"], body["temp_password"]).status_code == 400
    assert login(body["username"], SOCIETY_PASSWORD).status_code == 200


def test_changing_the_password_ends_every_other_session(world):
    body, client, _ = first_login(world)
    elsewhere = APIClient()
    login(body["username"], body["temp_password"], elsewhere)

    client.post(
        reverse("auth-change-password"),
        {"current_password": body["temp_password"], "new_password": SOCIETY_PASSWORD},
        format="json",
    )

    assert elsewhere.get(reverse("auth-me")).status_code == 403
    assert client.get(reverse("auth-me")).status_code == 200


@pytest.mark.parametrize(
    ("new_password", "why"),
    [
        ("short1", "too short"),
        ("12345678901", "entirely numeric"),
        ("password123", "too common"),
    ],
)
def test_weak_new_passwords_are_rejected(world, new_password, why):
    body, client, _ = first_login(world)

    response = client.post(
        reverse("auth-change-password"),
        {"current_password": body["temp_password"], "new_password": new_password},
        format="json",
    )

    assert response.status_code == 400, why
    assert "new_password" in response.json()
    assert User.objects.get(username=body["username"]).must_change_password is True


def test_a_wrong_current_password_is_rejected_and_nothing_changes(world):
    body, client, _ = first_login(world)

    response = client.post(
        reverse("auth-change-password"),
        {"current_password": "not-it-at-all", "new_password": SOCIETY_PASSWORD},
        format="json",
    )

    assert response.status_code == 400 and "current_password" in response.json()
    assert login(body["username"], body["temp_password"]).status_code == 200


def test_the_new_password_must_differ_from_the_old_one(world):
    body, client, _ = first_login(world)

    response = client.post(
        reverse("auth-change-password"),
        {"current_password": body["temp_password"], "new_password": body["temp_password"]},
        format="json",
    )

    assert response.status_code == 400 and "new_password" in response.json()


def test_changing_a_password_requires_being_logged_in(world):
    response = APIClient().post(
        reverse("auth-change-password"),
        {"current_password": "x", "new_password": SOCIETY_PASSWORD},
        format="json",
    )

    assert response.status_code == 403


def test_change_password_is_protected_by_csrf(world):
    body = create_login(world).json()
    client = APIClient(enforce_csrf_checks=True)
    login(body["username"], body["temp_password"], client)
    payload = {"current_password": body["temp_password"], "new_password": SOCIETY_PASSWORD}

    without = client.post(reverse("auth-change-password"), payload, format="json")
    token = client.get(reverse("auth-csrf")).json()["csrfToken"]
    with_token = client.post(
        reverse("auth-change-password"), payload, format="json", HTTP_X_CSRFTOKEN=token
    )

    assert without.status_code == 403 and with_token.status_code == 200


def test_change_password_attempts_are_throttled(world):
    body, client, _ = first_login(world)
    statuses = [
        client.post(
            reverse("auth-change-password"),
            {"current_password": "wrong-guess", "new_password": SOCIETY_PASSWORD},
            format="json",
        ).status_code
        for _ in range(12)
    ]

    assert statuses[:10] == [400] * 10 and 429 in statuses[10:]


# --- Expiry --------------------------------------------------------------------------------


def expire(username):
    User.objects.filter(username=username).update(
        temp_password_expires_at=timezone.now() - timedelta(minutes=1)
    )


def test_an_expired_temporary_password_cannot_log_in_even_if_correct(world):
    body = create_login(world).json()
    expire(body["username"])
    client = APIClient()

    response = login(body["username"], body["temp_password"], client)

    assert response.status_code == 400
    assert response.json()["code"] == "credentials_expired"
    assert client.get(reverse("auth-me")).status_code == 403  # no session was created


def test_expiry_does_not_reveal_which_usernames_exist(world):
    body = create_login(world).json()
    expire(body["username"])

    wrong_password = login(body["username"], "definitely-wrong")
    unknown_user = login("nobody@nowhere", "definitely-wrong")

    assert wrong_password.status_code == unknown_user.status_code == 400
    assert wrong_password.json() == unknown_user.json()


def test_an_unexpired_temporary_password_still_works_on_the_last_day(world):
    body = create_login(world).json()
    User.objects.filter(username=body["username"]).update(
        temp_password_expires_at=timezone.now() + timedelta(hours=1)
    )

    assert login(body["username"], body["temp_password"]).status_code == 200


def test_the_login_status_shown_to_the_admin_follows_the_lifecycle(world):
    body = create_login(world).json()
    status_of = lambda: next(  # noqa: E731
        m["login_status"]
        for m in world["admin"].get(members_url(world)).json()
        if m["user"] == body["username"]
    )

    assert status_of() == "temporary"
    expire(body["username"])
    assert status_of() == "expired"


# --- Re-issuing credentials ---------------------------------------------------------------


def member_of(body):
    return Membership.objects.get(user__username=body["username"])


def test_reissue_replaces_the_password_and_ends_existing_sessions(world):
    body, client, _ = first_login(world)
    client.post(
        reverse("auth-change-password"),
        {"current_password": body["temp_password"], "new_password": SOCIETY_PASSWORD},
        format="json",
    )
    assert client.get(reverse("auth-me")).status_code == 200  # signed in with their own password

    response = world["admin"].post(reissue_url(world, member_of(body).id))

    assert response.status_code == 200 and response["Cache-Control"] == "no-store"
    new_temp = response.json()["temp_password"]
    assert client.get(reverse("auth-me")).status_code == 403  # old session is gone
    assert login(body["username"], SOCIETY_PASSWORD).status_code == 400  # old password is dead
    assert login(body["username"], new_temp).json()["must_change_password"] is True


def test_reissue_is_audited_without_the_password(world):
    body = create_login(world).json()

    new_temp = world["admin"].post(reissue_url(world, member_of(body).id)).json()["temp_password"]

    row = AuditLog.objects.get(action="credentials.reissued")
    assert row.data == {"username": body["username"]}
    assert new_temp not in str(row.data)


def test_only_an_admin_can_reissue(world):
    body = create_login(world).json()

    response = client_for(world["people"]["tara"]).post(reissue_url(world, member_of(body).id))

    assert response.status_code == 403
    assert login(body["username"], body["temp_password"]).status_code == 200


def test_an_admin_cannot_reissue_for_someone_in_another_society(world):
    other = Society.objects.create(name="Lake View", slug="lake-view")
    flat = Flat.objects.create(society=other, label="B-1")
    stranger = make_user("stranger")
    foreign_member = add_member(society=other, user=stranger, role="resident", flat=flat)

    response = world["admin"].post(reissue_url(world, foreign_member.id))

    assert response.status_code == 404
    assert authenticate(username="stranger", password="pw-not-used-123") is not None


def test_reissue_refuses_a_person_who_also_belongs_to_another_society(world):
    """Otherwise society A's admin could take over an account that society B also relies on."""
    other = Society.objects.create(name="Lake View", slug="lake-view")
    shared = make_user("shared", password="their-own-Passphrase-9")
    other_flat = Flat.objects.create(society=other, label="B-1")
    add_member(society=other, user=shared, role="resident", flat=other_flat)
    mine = add_member(society=world["society"], user=shared, role="resident", flat=world["flat"])

    response = world["admin"].post(reissue_url(world, mine.id))

    assert response.status_code == 409
    assert authenticate(username="shared", password="their-own-Passphrase-9") is not None


@pytest.mark.parametrize("flags", [{"is_staff": True}, {"is_superuser": True}])
def test_reissue_never_touches_staff_or_superuser_accounts(world, flags):
    boss = make_user("boss", password="boss-Passphrase-123", **flags)
    member = add_member(society=world["society"], user=boss, role="admin")

    response = world["admin"].post(reissue_url(world, member.id))

    assert response.status_code == 409
    assert authenticate(username="boss", password="boss-Passphrase-123") is not None


def test_an_admin_cannot_reissue_their_own_login(world):
    me = Membership.objects.get(user=world["people"]["asha"])

    response = world["admin"].post(reissue_url(world, me.id))

    assert response.status_code == 409
    assert "Change password" in response.json()["detail"]


# --- Performance -----------------------------------------------------------------------------


def test_the_member_list_stays_constant_in_queries_with_the_new_fields(world):
    for i in range(3):
        create_login(world, name=f"Person{i}")

    def count():
        with CaptureQueriesContext(connection) as ctx:
            assert world["admin"].get(members_url(world)).status_code == 200
        return len(ctx)

    baseline = count()
    for i in range(5):
        create_login(world, name=f"Another{i}")

    assert count() == baseline
