"""Demo mode: one-click logins for visitors who have no credentials (recruiters, reviewers).

This is a deliberate hole in authentication, so it is locked down hard:
  * OFF unless DEMO_MODE=True is set in the environment (default False);
  * works ONLY for usernames listed in DEMO_USERS, exact match;
  * never for inactive accounts, and never for staff or superusers (Django admin access),
    even if one is on the list;
  * no password is ever published anywhere; the browser just asks to be logged in as one of
    the listed accounts.
Use it only against a database that holds fake data. A system check warns whenever it is on.
"""

from django.conf import settings
from django.contrib.auth import get_user_model

from apps.societies.models import Membership

ROLE_ORDER = {"president": 0, "secretary": 1, "treasurer": 2, "resident": 3}


def demo_enabled() -> bool:
    return bool(settings.DEMO_MODE and settings.DEMO_USERS)


def demo_users():
    """The ONLY accounts demo login may ever return. Everything else is excluded here."""
    return get_user_model().objects.filter(
        username__in=settings.DEMO_USERS,
        is_active=True,
        is_staff=False,
        is_superuser=False,
    )


def demo_accounts() -> list[dict]:
    """One entry per demo user (their first membership), most senior role first."""
    seen, accounts = set(), []
    memberships = (
        Membership.objects.filter(user__in=demo_users())
        .select_related("user", "society", "flat")
        .order_by("id")
    )
    for m in memberships:
        if m.user_id in seen:
            continue
        seen.add(m.user_id)
        accounts.append(
            {
                "username": m.user.username,
                "role": m.role,
                "society_name": m.society.name,
                "flat_label": m.flat.label if m.flat else None,
            }
        )
    return sorted(accounts, key=lambda a: (ROLE_ORDER[a["role"]], a["username"]))
