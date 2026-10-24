"""Check uploaded rows, and create the flats, people and logins from them in ONE transaction.

Two entry points, and the second does NOT trust the first:
* clean_rows(): validates rows and returns (clean rows, errors). Used by the preview, which
  writes nothing, and again by the confirm.
* import_flats_and_people(): locks the society, re-runs clean_rows() on whatever the client
  sent, and only then creates anything. The browser could have edited the preview, or another
  import could have created the same flat in the meantime, so the checks run again inside the
  lock, never once at preview time and then assumed.

Rules of this first version: flats are created, never updated (a label that already exists is an
error); one row per person; a flat with several people repeats its row and the amount must match.
"""

import re
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction

from apps.audit import services as audit
from apps.audit.models import AuditLog
from apps.core.money import CENT
from apps.societies.models import Flat, Membership, Society
from apps.societies.services import create_member_login

MAX_AMOUNT = Decimal("9999999999.99")  # Flat.maintenance_amount is max_digits=12, decimal_places=2
ROLES = [value for value, _label in Membership.Role.choices]
FIELDS = ("flat", "name", "phone", "email", "maintenance", "role")


class ImportInvalid(Exception):
    """The rows have problems. `errors` is a list of {row, field, message}."""

    def __init__(self, errors):
        self.errors = errors
        super().__init__(f"{len(errors)} problem(s) in the file")


def _amount(text):
    """'₹4,500' -> Decimal('4500.00'). Raises ValueError with a plain-language reason."""
    cleaned = re.sub(r"(?i)(₹|rs\.?|inr)", "", text).replace(",", "").strip()
    if not cleaned:
        raise ValueError("Enter the maintenance amount for this flat.")
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        raise ValueError(f"'{text}' is not an amount. Use digits like 4500 or 4500.50.") from None
    if not value.is_finite() or value < 0:
        raise ValueError("The amount cannot be negative.")
    if value != value.quantize(CENT):
        raise ValueError("Use at most 2 decimal places (paise).")
    if value > MAX_AMOUNT:
        raise ValueError("This amount is too large.")
    return value.quantize(CENT)


def _phone(text):
    """Keep digits and a leading +; 7 to 15 digits. '' means no phone number."""
    if not text:
        return ""
    plus = "+" if text.strip().startswith("+") else ""
    digits = re.sub(r"\D", "", text)
    if not 7 <= len(digits) <= 15:
        raise ValueError("The phone number should have 7 to 15 digits.")
    return plus + digits


def _email(text):
    if not text:
        return ""
    try:
        validate_email(text)
    except ValidationError:
        raise ValueError(f"'{text}' is not a valid email address.") from None
    if len(text) > 254:
        raise ValueError("This email address is too long.")
    return text.lower()


def clean_rows(society, raw_rows):
    """Validate rows for `society`. Returns (clean_rows, errors); never writes anything.

    Each raw row is {"row": spreadsheet row number, "flat", "name", "phone", "email",
    "maintenance", "role"} (all text, any may be missing). A clean row has the same keys with
    normalised values, and `maintenance` as a "4500.00" string.
    """
    existing = {
        label.casefold()
        for label in Flat.objects.for_society(society).values_list("label", flat=True)
    }
    seen = {}  # casefolded flat label -> (spelling, amount, first row)
    clean, errors = [], []

    for raw in raw_rows:
        number = raw.get("row", 0)
        row_errors = []

        def fail(field, message, _n=number, _e=row_errors):
            _e.append({"row": _n, "field": field, "message": message})

        value = {f: " ".join(str(raw.get(f) or "").split()) for f in FIELDS}

        label = value["flat"]
        if not label:
            fail("flat", "Enter the flat number.")
        elif len(label) > 20:
            fail("flat", "The flat number is too long (20 characters at most).")
        elif label.casefold() in existing:
            fail("flat", f"Flat {label} already exists. Edit it on the Flats page instead.")

        if not value["name"]:
            fail("name", "Enter the person's name.")
        elif len(value["name"]) > 100:
            fail("name", "The name is too long (100 characters at most).")

        amount = None
        try:
            amount = _amount(value["maintenance"])
        except ValueError as exc:
            fail("maintenance", str(exc))
        phone = email = ""
        try:
            phone = _phone(value["phone"])
        except ValueError as exc:
            fail("phone", str(exc))
        try:
            email = _email(value["email"])
        except ValueError as exc:
            fail("email", str(exc))

        role = (value["role"] or "resident").lower()
        if role not in ROLES:
            fail("role", "The role must be one of: " + ", ".join(ROLES) + ".")

        if label and amount is not None and not row_errors:
            key = label.casefold()
            if key in seen:
                spelling, first_amount, first_row = seen[key]
                if amount != first_amount:
                    fail(
                        "maintenance",
                        f"Flat {spelling} has two different amounts ({first_amount} on row "
                        f"{first_row}, {amount} here). Every person in a flat shares one amount.",
                    )
                label = spelling  # 'a-101' and 'A-101' are one flat
            else:
                seen[key] = (label, amount, number)

        if row_errors:
            errors.extend(row_errors)
        else:
            clean.append(
                {
                    "row": number,
                    "flat": label,
                    "name": value["name"],
                    "phone": phone,
                    "email": email,
                    "maintenance": format(amount, "f"),
                    "role": role,
                }
            )
    return clean, errors


def summarize(clean):
    """Counts for the preview. The amount is counted once per flat, not once per person."""
    per_flat = {}
    for row in clean:
        per_flat.setdefault(row["flat"].casefold(), Decimal(row["maintenance"]))
    return {
        "flats": len(per_flat),
        "people": len(clean),
        "total_per_cycle": format(sum(per_flat.values(), Decimal("0.00")), "f"),
    }


@transaction.atomic
def import_flats_and_people(*, society, actor, rows):
    """Create every flat, person and login in `rows`, or nothing. Returns the one-time logins.

    Raises ImportInvalid if anything fails validation (nothing is written then).
    """
    # One import per society at a time. A second import waits here, then re-validates against
    # the flats the first one created, instead of colliding halfway through.
    Society.objects.select_for_update().get(pk=society.pk)

    clean, errors = clean_rows(society, rows)
    if not errors and not clean:
        errors = [{"row": 0, "field": "file", "message": "There are no rows to import."}]
    if errors:
        raise ImportInvalid(errors)

    flats = {}
    for row in clean:
        key = row["flat"].casefold()
        if key not in flats:
            flats[key] = Flat.objects.create(
                society=society,
                label=row["flat"],
                maintenance_amount=Decimal(row["maintenance"]),
            )

    logins = []
    for row in clean:
        flat = flats[row["flat"].casefold()]
        membership, password = create_member_login(
            society=society,
            actor=actor,
            name=row["name"],
            role=row["role"],
            flat=flat,
            phone=row["phone"],
            email=row["email"],
        )
        logins.append(
            {
                "name": membership.user.first_name,
                "flat": flat.label,
                "role": row["role"],
                "username": membership.user.username,
                "temp_password": password,
                "expires_at": membership.user.temp_password_expires_at,
            }
        )

    # Counts only. Names, phone numbers and email addresses never go into the audit log.
    audit.record(
        society=society,
        actor=actor,
        action=AuditLog.Action.SOCIETY_IMPORTED,
        object_type="society",
        object_id=society.pk,
        data={"flats": len(flats), "people": len(logins)},
    )
    return {"flats": len(flats), "people": len(logins), "logins": logins}
