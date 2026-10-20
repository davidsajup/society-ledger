import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.checks import demo_mode_is_loud
from apps.societies.models import Flat, Society
from apps.societies.services import add_member

pytestmark = pytest.mark.django_db

INFO, LOGIN, ME = "auth-demo", "auth-demo-login", "auth-me"
ALLOWLIST = ["asha", "tara", "ravi", "nisha", "root", "stafferd", "ghost", "missing"]


def make_user(name, **extra):
    return get_user_model().objects.create_user(username=name, password="never-used", **extra)


@pytest.fixture
def world():
    society = Society.objects.create(name="Sunrise Heights", slug="sunrise-heights")
    a1 = Flat.objects.create(society=society, label="A-101")
    a2 = Flat.objects.create(society=society, label="A-102")
    people = {name: make_user(name) for name in ("asha", "tara", "ravi", "nisha", "boss")}
    add_member(society=society, user=people["asha"], role="secretary")
    add_member(society=society, user=people["tara"], role="treasurer")
    add_member(society=society, user=people["ravi"], role="resident", flat=a1)
    add_member(society=society, user=people["nisha"], role="resident", flat=a2)
    add_member(society=society, user=people["boss"], role="secretary")  # NOT on the allowlist
    # Accounts that are on the allowlist but must still be refused:
    make_user("root", is_superuser=True, is_staff=True)
    make_user("stafferd", is_staff=True)
    make_user("ghost", is_active=False)
    return {"society": society, "people": people}


@pytest.fixture
def demo_on(settings):
    settings.DEMO_MODE = True
    settings.DEMO_USERS = ALLOWLIST


def info(client=None):
    return (client or APIClient()).get(reverse(INFO))


def demo_login(username, client=None):
    return (client or APIClient()).post(reverse(LOGIN), {"username": username}, format="json")


# --- Off by default -------------------------------------------------------------------------


def test_demo_mode_is_off_by_default_and_says_so(world):
    response = info()

    assert response.status_code == 200
    assert response.json() == {"enabled": False, "accounts": []}


def test_demo_login_does_not_exist_when_demo_mode_is_off(world):
    client = APIClient()

    response = demo_login("tara", client)

    assert response.status_code == 404
    assert client.get(reverse(ME)).status_code == 403  # no session was created


def test_demo_mode_with_an_empty_allowlist_is_treated_as_off(world, settings):
    settings.DEMO_MODE = True
    settings.DEMO_USERS = []

    assert info().json()["enabled"] is False
    assert demo_login("tara").status_code == 404


# --- What the login page is told -------------------------------------------------------------


def test_info_lists_only_safe_allowlisted_accounts_in_a_sensible_order(world, demo_on):
    accounts = info().json()["accounts"]

    assert [(a["username"], a["role"]) for a in accounts] == [
        ("asha", "secretary"),
        ("tara", "treasurer"),
        ("nisha", "resident"),
        ("ravi", "resident"),
    ]
    by_name = {a["username"]: a for a in accounts}
    assert by_name["ravi"]["flat_label"] == "A-101"
    assert by_name["tara"]["flat_label"] is None
    assert by_name["tara"]["society_name"] == "Sunrise Heights"


def test_info_never_reveals_staff_inactive_unlisted_or_missing_accounts(world, demo_on):
    names = {a["username"] for a in info().json()["accounts"]}

    assert not names & {"root", "stafferd", "ghost", "boss", "missing"}


def test_info_contains_no_secrets(world, demo_on):
    body = info().content.decode().lower()

    assert "password" not in body and "never-used" not in body


# --- Logging in ------------------------------------------------------------------------------


def test_an_allowlisted_user_is_logged_in_without_a_password(world, demo_on):
    client = APIClient()

    response = demo_login("tara", client)

    assert response.status_code == 200
    assert response.json()["username"] == "tara"
    assert response.json()["memberships"][0]["role"] == "treasurer"
    assert client.get(reverse(ME)).json()["username"] == "tara"  # a real session now exists


def test_a_demo_session_is_a_normal_session_with_normal_permissions(world, demo_on):
    society_id = world["society"].id
    summary = reverse("summary", kwargs={"society_id": society_id})
    resident, treasurer = APIClient(), APIClient()
    demo_login("nisha", resident)
    demo_login("tara", treasurer)

    assert resident.get(summary).status_code == 403  # a resident is still only a resident
    assert treasurer.get(summary).status_code == 200


@pytest.mark.parametrize("username", ["boss", "root", "stafferd", "ghost"])
def test_demo_login_refuses_everyone_who_is_not_a_safe_listed_user(world, demo_on, username):
    """Proves: the endpoint cannot be used to become an unlisted admin, a Django staff or
    superuser, or a deactivated account, even when the name is on the allowlist."""
    client = APIClient()

    response = demo_login(username, client)

    assert response.status_code == 404
    assert client.get(reverse(ME)).status_code == 403


def test_unknown_and_refused_users_get_identical_answers(world, demo_on):
    unknown = demo_login("nobody-by-that-name")
    refused = demo_login("boss")

    assert unknown.status_code == refused.status_code == 404
    assert unknown.json() == refused.json()


@pytest.mark.parametrize("username", ["TARA", "Tara", "ta", "tarax", "tara' OR '1'='1", "%", "*"])
def test_the_username_must_match_exactly(world, demo_on, username):
    """No case-insensitive, partial or wildcard matching."""
    assert demo_login(username).status_code == 404


def test_surrounding_spaces_are_trimmed_but_never_widen_who_can_log_in(world, demo_on):
    padded_listed = APIClient()
    padded_unlisted = APIClient()

    assert demo_login("  tara  ", padded_listed).json()["username"] == "tara"
    assert demo_login("  boss  ", padded_unlisted).status_code == 404
    assert padded_unlisted.get(reverse(ME)).status_code == 403


def test_a_request_without_a_username_is_a_400(world, demo_on):
    response = APIClient().post(reverse(LOGIN), {}, format="json")

    assert response.status_code == 400


def test_demo_login_is_throttled(world, demo_on):
    client = APIClient()
    statuses = [demo_login("tara", client).status_code for _ in range(32)]

    assert 429 in statuses[30:]


# --- The loud warning --------------------------------------------------------------------


def test_the_system_check_warns_loudly_when_demo_mode_is_on(world, demo_on):
    (warning,) = demo_mode_is_loud(None)

    assert warning.id == "accounts.W001"
    assert "without a password" in warning.msg and "tara" in warning.msg


def test_the_system_check_is_silent_when_demo_mode_is_off(world):
    assert demo_mode_is_loud(None) == []
