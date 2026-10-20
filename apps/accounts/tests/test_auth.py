import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from apps.societies.models import Flat, Society
from apps.societies.services import add_member

pytestmark = pytest.mark.django_db

LOGIN = "auth-login"


@pytest.fixture
def society():
    return Society.objects.create(name="Green Park", slug="green-park")


@pytest.fixture
def admin_user(society):
    user = get_user_model().objects.create_user(username="asha", password="correct-horse")
    add_member(society=society, user=user, role="secretary")
    return user


def login(client, username="asha", password="correct-horse"):
    return client.post(reverse(LOGIN), {"username": username, "password": password})


def test_login_returns_identity_and_memberships(admin_user, society):
    response = login(APIClient())

    assert response.status_code == 200
    assert response.data["username"] == "asha"
    assert response.data["memberships"] == [
        {
            "society_id": society.id,
            "society_name": "Green Park",
            "role": "secretary",
            "flat_id": None,
            "flat_label": None,
        }
    ]


def test_me_requires_login_and_works_after_it(admin_user):
    client = APIClient()
    assert client.get(reverse("auth-me")).status_code == 403

    login(client)

    assert client.get(reverse("auth-me")).status_code == 200


def test_me_only_returns_the_callers_own_memberships(admin_user, society):
    other = get_user_model().objects.create_user(username="ravi", password="pw-ravi-123")
    flat = Flat.objects.create(society=society, label="A-1")
    add_member(society=society, user=other, role="resident", flat=flat)
    client = APIClient()
    login(client)

    roles = [m["role"] for m in client.get(reverse("auth-me")).data["memberships"]]

    assert roles == ["secretary"]


def test_wrong_password_and_unknown_user_look_identical(admin_user):
    wrong_password = login(APIClient(), password="nope")
    unknown_user = login(APIClient(), username="ghost", password="nope")

    assert wrong_password.status_code == unknown_user.status_code == 400
    assert wrong_password.data == unknown_user.data


def test_inactive_user_cannot_log_in(admin_user):
    admin_user.is_active = False
    admin_user.save()

    assert login(APIClient()).status_code == 400


def test_logout_ends_the_session(admin_user):
    client = APIClient()
    login(client)

    assert client.post(reverse("auth-logout")).status_code == 204
    assert client.get(reverse("auth-me")).status_code == 403


def test_login_is_throttled_after_repeated_failures(admin_user):
    client = APIClient()
    statuses = [login(client, password="nope").status_code for _ in range(12)]

    assert statuses[:10] == [400] * 10
    assert 429 in statuses[10:]
    # Even the right password is refused while throttled.
    assert login(client).status_code == 429


def test_session_writes_require_a_csrf_token(admin_user, society):
    """Cookies are sent automatically by browsers, so a write without the token must fail."""
    client = APIClient(enforce_csrf_checks=True)
    login(client)
    url = reverse("flat-list", kwargs={"society_id": society.id})

    without_token = client.post(url, {"label": "A-101"})
    token = client.get(reverse("auth-csrf")).data["csrfToken"]
    with_token = client.post(url, {"label": "A-101"}, HTTP_X_CSRFTOKEN=token)

    assert without_token.status_code == 403
    assert with_token.status_code == 201
