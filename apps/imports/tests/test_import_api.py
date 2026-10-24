"""The bulk import end to end: preview, confirm, who may use it, and what it must never leak.

What these tests prove
* PREVIEW writes nothing, however bad the file.
* CONFIRM is all-or-nothing: one bad row anywhere means no flat, no person, no login, no audit row.
* The server does not trust the browser: it re-checks every row on confirm, inside a per-society
  lock, so an edited preview, a flat created in the meantime, a double click, or two imports at
  once cannot produce duplicates or half an import.
* Only a president or secretary of THAT society can import; the super admin, treasurers, residents
  and other societies cannot.
* Phone numbers and email addresses are stored per society, shown only to managers, and never
  appear in the audit log, the super admin's list or any resident's data.
* Temporary passwords exist in the confirm response only.
"""

import io
import threading
import time
from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from openpyxl import Workbook
from rest_framework.test import APIClient

from apps.audit.models import AuditLog
from apps.imports import services
from apps.imports.parsing import MAX_FILE_BYTES, MAX_ROWS
from apps.imports.services import ImportInvalid, import_flats_and_people
from apps.societies.models import Flat, Membership
from apps.societies.services import add_member, create_society

User = get_user_model()
D = Decimal

CSV = (
    "Flat,Name,Phone,Email,Maintenance\n"
    "A-101,Ravi Kumar,98765 43210,ravi@example.com,4500\n"
    "A-102,Meena Iyer,+91 99999 11111,meena@example.com,4500\n"
    "A-103,Sunil Shah,,,6000.50\n"
)


@pytest.fixture
def world(db):
    """A quarterly society made by a super admin, its settled president, and a stranger society."""
    root = User.objects.create_superuser(username="root", password="x")
    society, president, _ = create_society(
        actor=root,
        name="Green Meadows",
        slug="green-meadows",
        president_name="Vikram Rao",
        billing_cycle_months=3,
        billing_start=date(date.today().year + 1, 1, 1),
    )
    president.user.must_change_password = False
    president.user.save()
    other, other_president, _ = create_society(
        actor=root, name="Lake View", slug="lake-view", president_name="Anil Shah"
    )
    other_president.user.must_change_password = False
    other_president.user.save()
    return {
        "root": root,
        "society": society,
        "president": president.user,
        "other": other,
        "other_president": other_president.user,
    }


def client_for(user=None):
    client = APIClient()
    if user is not None:
        client.force_authenticate(user=user)
    return client


def preview_url(society):
    return reverse("import-preview", kwargs={"society_id": society.id})


def confirm_url(society):
    return reverse("import-confirm", kwargs={"society_id": society.id})


def upload(client, society, data=CSV, name="flats.csv"):
    payload = data.encode() if isinstance(data, str) else data
    return client.post(
        preview_url(society), {"file": SimpleUploadedFile(name, payload)}, format="multipart"
    )


def counts():
    return (
        Flat.objects.count(),
        Membership.objects.count(),
        User.objects.count(),
        AuditLog.objects.count(),
    )


def previewed_rows(world, data=CSV):
    return upload(client_for(world["president"]), world["society"], data).data["rows"]


# --- Preview ----------------------------------------


def test_preview_describes_the_file_and_writes_nothing(world):
    before = counts()

    response = upload(client_for(world["president"]), world["society"])

    assert response.status_code == 200
    assert response["Cache-Control"] == "no-store"
    assert response.data["errors"] == []
    assert response.data["summary"] == {"flats": 3, "people": 3, "total_per_cycle": "15000.50"}
    assert response.data["cycle_months"] == 3
    assert response.data["rows"][0] == {
        "row": 2,
        "flat": "A-101",
        "name": "Ravi Kumar",
        "phone": "9876543210",
        "email": "ravi@example.com",
        "maintenance": "4500.00",
        "role": "resident",
    }
    assert counts() == before


def test_preview_reports_every_problem_and_still_writes_nothing(world):
    before = counts()
    bad = (
        "Flat,Name,Email,Maintenance\n"
        "A-1,Ravi,not-an-email,4500\n"
        "A-2,,x@y.in,abc\n"
        "A-3,Meena,m@y.in,4500\n"
    )

    response = upload(client_for(world["president"]), world["society"], bad)

    assert response.status_code == 200
    assert [(e["row"], e["field"]) for e in response.data["errors"]] == [
        (2, "email"),
        (3, "name"),
        (3, "maintenance"),
    ]
    assert [r["flat"] for r in response.data["rows"]] == ["A-3"]
    assert counts() == before


def test_an_excel_upload_works_end_to_end(world):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Flat No", "Tenant Name", "Mobile", "Email", "Maintenance Fees"])
    sheet.append(["B-201", "Kiran Rao", 9876501234, "kiran@example.com", 5400.0])
    out = io.BytesIO()
    workbook.save(out)
    client = client_for(world["president"])

    preview = upload(client, world["society"], out.getvalue(), "flats.xlsx")
    confirmed = client.post(
        confirm_url(world["society"]), {"rows": preview.data["rows"]}, format="json"
    )

    assert preview.data["errors"] == []
    assert confirmed.status_code == 201
    flat = Flat.objects.get(society=world["society"], label="B-201")
    assert flat.maintenance_amount == D("5400.00")


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"data": b"x", "name": "flats.xls"}, r"\.csv or \.xlsx"),
        ({"data": b"x" * (MAX_FILE_BYTES + 1), "name": "flats.csv"}, "larger than 1 MB"),
        ({"data": "Flat,Phone\nA-1,123\n", "name": "flats.csv"}, "tenant name"),
    ],
)
def test_unusable_files_are_a_400_with_a_plain_reason(world, kwargs, message):
    response = upload(client_for(world["president"]), world["society"], **kwargs)

    assert response.status_code == 400
    assert any(__import__("re").search(message, m) for m in response.data["file"])


def test_a_request_without_a_file_is_a_400(world):
    response = client_for(world["president"]).post(
        preview_url(world["society"]), {}, format="multipart"
    )

    assert response.status_code == 400 and "file" in response.data


def test_preview_only_accepts_a_multipart_upload(world):
    response = client_for(world["president"]).post(
        preview_url(world["society"]), {"file": "x"}, format="json"
    )

    assert response.status_code == 415


# --- Confirm ----------------------------------------


def test_confirm_creates_the_flats_people_and_logins(world):
    client = client_for(world["president"])
    rows = previewed_rows(world)

    response = client.post(confirm_url(world["society"]), {"rows": rows}, format="json")

    assert response.status_code == 201
    assert response["Cache-Control"] == "no-store"
    assert (response.data["flats"], response.data["people"]) == (3, 3)
    flats = {f.label: f.maintenance_amount for f in Flat.objects.for_society(world["society"])}
    assert flats == {"A-101": D("4500.00"), "A-102": D("4500.00"), "A-103": D("6000.50")}
    ravi = Membership.objects.get(society=world["society"], user__first_name="Ravi Kumar")
    assert (ravi.role, ravi.flat.label) == ("resident", "A-101")
    assert (ravi.phone, ravi.email) == ("9876543210", "ravi@example.com")


def test_each_login_works_once_and_must_be_changed(world):
    rows = previewed_rows(world)
    response = client_for(world["president"]).post(
        confirm_url(world["society"]), {"rows": rows}, format="json"
    )

    for login in response.data["logins"]:
        user = User.objects.get(username=login["username"])
        assert user.check_password(login["temp_password"])
        assert user.must_change_password is True
        assert user.username.endswith("@green-meadows")
        assert login["expires_at"]
    # a resident on a temporary password cannot use the app until they change it
    first = User.objects.get(username=response.data["logins"][0]["username"])
    blocked = client_for(first).get(
        reverse("flat-list", kwargs={"society_id": world["society"].id})
    )
    assert blocked.status_code == 403 and blocked.data["code"] == "password_change_required"


def test_passwords_are_never_stored_or_listed_again(world):
    client = client_for(world["president"])
    response = client.post(
        confirm_url(world["society"]), {"rows": previewed_rows(world)}, format="json"
    )
    passwords = [login["temp_password"] for login in response.data["logins"]]

    audit = str(list(AuditLog.objects.values_list("data", flat=True)))
    members = client.get(reverse("member-list", kwargs={"society_id": world["society"].id}))

    for password in passwords:
        assert password not in audit
        assert password not in members.content.decode()


def test_one_bad_row_creates_nothing_at_all(world):
    rows = previewed_rows(world)
    rows[2]["maintenance"] = "-1"  # the LAST row is bad: the first two must not survive it
    before = counts()

    response = client_for(world["president"]).post(
        confirm_url(world["society"]), {"rows": rows}, format="json"
    )

    assert response.status_code == 400
    assert response.data["errors"][0]["row"] == 4
    assert counts() == before


def test_the_server_rechecks_rows_the_browser_sends(world):
    """The preview was fine, but the request body is whatever the client chooses to send."""
    Flat.objects.create(society=world["society"], label="TAKEN")
    rows = previewed_rows(world)
    rows[0]["flat"] = "TAKEN"  # collides with an existing flat
    rows[1]["email"] = "not-an-email"  # a value the preview never allowed
    rows[2]["role"] = "emperor"
    before = counts()

    response = client_for(world["president"]).post(
        confirm_url(world["society"]), {"rows": rows}, format="json"
    )

    assert response.status_code == 400
    assert {e["field"] for e in response.data["errors"]} == {"flat", "email", "role"}
    assert counts() == before


def test_a_flat_created_between_preview_and_confirm_is_caught(world):
    rows = previewed_rows(world)
    Flat.objects.create(society=world["society"], label="A-102")  # someone adds it meanwhile
    before = counts()

    response = client_for(world["president"]).post(
        confirm_url(world["society"]), {"rows": rows}, format="json"
    )

    assert response.status_code == 400
    assert "already exists" in response.data["errors"][0]["message"]
    assert counts() == before


def test_confirming_twice_does_not_create_anything_twice(world):
    client = client_for(world["president"])
    rows = previewed_rows(world)
    first = client.post(confirm_url(world["society"]), {"rows": rows}, format="json")
    after_first = counts()

    second = client.post(confirm_url(world["society"]), {"rows": rows}, format="json")

    assert (first.status_code, second.status_code) == (201, 400)
    assert counts() == after_first


@pytest.mark.parametrize("rows", [[], None, "nope"])
def test_confirm_needs_rows(world, rows):
    response = client_for(world["president"]).post(
        confirm_url(world["society"]), {"rows": rows}, format="json"
    )

    assert response.status_code == 400


def test_confirm_refuses_more_than_300_rows(world):
    rows = [
        {"row": n, "flat": f"F-{n}", "name": "P", "maintenance": "1"} for n in range(MAX_ROWS + 1)
    ]

    response = client_for(world["president"]).post(
        confirm_url(world["society"]), {"rows": rows}, format="json"
    )

    assert response.status_code == 400
    assert Flat.objects.filter(society=world["society"]).count() == 0


# --- Audit and privacy ----------------------------------------


def test_the_audit_log_records_counts_only(world):
    client_for(world["president"]).post(
        confirm_url(world["society"]), {"rows": previewed_rows(world)}, format="json"
    )

    imported = AuditLog.objects.get(action="society.imported")
    assert imported.data == {"flats": 3, "people": 3}
    assert imported.actor_id == world["president"].id
    assert AuditLog.objects.filter(action="member.created", society=world["society"]).count() == 4
    everything = str(list(AuditLog.objects.values_list("data", flat=True)))
    for private in ("9876543210", "ravi@example.com", "meena@example.com", "99999", "Ravi Kumar"):
        assert private not in everything


def test_only_managers_see_contact_details_and_never_other_societies_or_the_super_admin(world):
    president = client_for(world["president"])
    president.post(confirm_url(world["society"]), {"rows": previewed_rows(world)}, format="json")
    ravi = User.objects.get(first_name="Ravi Kumar")
    ravi.must_change_password = False
    ravi.save()

    managers_view = president.get(
        reverse("member-list", kwargs={"society_id": world["society"].id})
    )
    assert "ravi@example.com" in managers_view.content.decode()

    platform = client_for(world["root"]).get(reverse("platform-society-list")).content.decode()
    other_view = (
        client_for(world["other_president"])
        .get(reverse("member-list", kwargs={"society_id": world["other"].id}))
        .content.decode()
    )
    resident_me = client_for(ravi).get(reverse("auth-me")).content.decode()
    resident_members = client_for(ravi).get(
        reverse("member-list", kwargs={"society_id": world["society"].id})
    )
    for private in ("ravi@example.com", "9876543210", "meena@example.com"):
        assert private not in platform
        assert private not in other_view
        assert private not in resident_me
    assert resident_members.status_code == 403  # residents cannot list members at all


# --- Who may import ----------------------------------------


@pytest.mark.parametrize("route", ["import-preview", "import-confirm"])
def test_the_super_admin_cannot_import_into_a_society(world, route):
    url = reverse(route, kwargs={"society_id": world["society"].id})

    assert client_for(world["root"]).post(url, {"rows": []}, format="json").status_code == 404


@pytest.mark.parametrize("role", ["treasurer", "resident"])
@pytest.mark.parametrize("route", ["import-preview", "import-confirm"])
def test_treasurers_and_residents_are_refused(world, role, route):
    user = User.objects.create_user(username=f"u-{role}", password="x")
    flat = Flat.objects.create(society=world["society"], label="Z-1")
    add_member(
        society=world["society"], user=user, role=role, flat=flat if role == "resident" else None
    )
    before = counts()

    response = client_for(user).post(
        reverse(route, kwargs={"society_id": world["society"].id}), {"rows": []}, format="json"
    )

    assert response.status_code == 403
    assert counts() == before


def test_a_secretary_may_import_too(world):
    secretary = User.objects.create_user(username="sec", password="x")
    add_member(society=world["society"], user=secretary, role="secretary")

    response = upload(client_for(secretary), world["society"])

    assert response.status_code == 200


def test_the_president_of_another_society_gets_a_404(world):
    response = upload(client_for(world["other_president"]), world["society"])

    assert response.status_code == 404
    assert Flat.objects.count() == 0


def test_anonymous_callers_and_unsettled_presidents_are_refused(world):
    assert upload(client_for(), world["society"]).status_code == 403
    world["president"].must_change_password = True
    world["president"].save()
    assert upload(client_for(world["president"]), world["society"]).status_code == 403


def test_imports_are_throttled(world):
    client = client_for(world["president"])
    statuses = [
        client.post(preview_url(world["society"]), {}, format="multipart").status_code
        for _ in range(61)
    ]

    assert statuses[:60] == [400] * 60  # a missing file is a 400, 60 times
    assert statuses[60] == 429


# --- Two imports at once ----------------------------------------


@pytest.mark.django_db(transaction=True)
def test_two_simultaneous_imports_of_the_same_file_create_one_set_of_flats(world, monkeypatch):
    """Both validate before either creates, unless the society lock makes the second wait.

    The sleep opens the window between 'checked it is fine' and 'created it'. With the lock the
    second import waits, re-checks, finds the flats exist and is refused cleanly. Without it both
    pass the check and the second crashes on the database's unique constraint (or duplicates).
    """
    rows = previewed_rows(world)
    real = services.clean_rows

    def slow(society, raw_rows):
        result = real(society, raw_rows)
        time.sleep(0.2)
        return result

    monkeypatch.setattr(services, "clean_rows", slow)
    outcomes = []
    barrier = threading.Barrier(2)

    def attempt():
        from django.db import connection

        try:
            barrier.wait(timeout=10)
            import_flats_and_people(society=world["society"], actor=world["president"], rows=rows)
            outcomes.append("created")
        except ImportInvalid:
            outcomes.append("refused")
        except Exception as exc:  # noqa: BLE001 - anything else is the failure we are hunting
            outcomes.append(type(exc).__name__)
        finally:
            connection.close()

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert sorted(outcomes) == ["created", "refused"]
    assert Flat.objects.filter(society=world["society"]).count() == 3
    assert Membership.objects.filter(society=world["society"]).count() == 4  # 3 people + president
