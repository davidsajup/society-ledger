"""Temporary credentials for admin-issued logins.

Rules this module enforces:
  * the password is RANDOM, never derived from anything about the person or their flat;
  * it is shown to the admin once, and stored only as a hash (set_password);
  * it expires, and must be replaced at first login (see permissions.IsSettledUser).
"""

import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.text import slugify

# No 0/o, 1/l/i: slips get typed by hand and read aloud.
_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"


def generate_temp_password() -> str:
    """12 random characters from a 31-letter alphabet (about 59 bits), as xxxx-xxxx-xxxx."""
    chars = "".join(secrets.choice(_ALPHABET) for _ in range(12))
    return "-".join(chars[i : i + 4] for i in range(0, 12, 4))


def set_temporary_password(user) -> str:
    """Give `user` a fresh random temporary password and return it (the ONLY time it exists)."""
    password = generate_temp_password()
    user.set_password(password)
    user.must_change_password = True
    user.temp_password_expires_at = timezone.now() + timedelta(days=settings.TEMP_PASSWORD_DAYS)
    return password


def temp_password_expired(user) -> bool:
    return bool(
        user.must_change_password
        and user.temp_password_expires_at is not None
        and user.temp_password_expires_at < timezone.now()
    )


def login_status(user) -> str:
    """'active' (chose their own password), 'temporary' (not yet used) or 'expired'."""
    if not user.must_change_password:
        return "active"
    return "expired" if temp_password_expired(user) else "temporary"


def make_username(society, name: str, flat_label: str | None, role: str) -> str:
    """A readable, globally unique username such as 'ravi.a-101@sunrise-heights'.

    It is an identifier, not a secret. The society slug keeps two societies' 'A-101' apart.
    """
    who = slugify(name).split("-")[0] or "member"
    where = slugify(flat_label) if flat_label else role
    base = f"{who}.{where}"
    User = get_user_model()
    candidate, n = f"{base}@{society.slug}", 1
    while User.objects.filter(username=candidate).exists():
        n += 1
        candidate = f"{base}.{n}@{society.slug}"
    return candidate
