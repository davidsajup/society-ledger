"""The 'admin' role became 'secretary' in migration 0004. This rehearses it on real rows.

It matters because the same migration will run against a live database: the data must be
converted while no role CHECK exists (the old CHECK rejects the new names, the new CHECK
rejects leftover 'admin' rows), and it must be reversible.
"""

import pytest
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor

BEFORE = [("societies", "0003_flat_monthly_maintenance_and_more")]
AFTER = [("societies", "0004_office_bearer_roles")]
# The user table keeps its newer columns whichever societies migration we stop at, so the
# historical models must be built from both nodes or inserts would miss those columns.
ACCOUNTS = [("accounts", "0002_user_must_change_password_and_more")]


def migrate(targets):
    """Move the societies app to `targets` and return the historical models at that point."""
    executor = MigrationExecutor(connection)
    executor.migrate(targets)
    return MigrationExecutor(connection).loader.project_state(targets + ACCOUNTS).apps


def restore_database():
    """Leave the shared test database fully migrated for every other test."""
    executor = MigrationExecutor(connection)
    executor.migrate(executor.loader.graph.leaf_nodes())


def roles_by_username(apps):
    membership = apps.get_model("societies", "Membership")
    return dict(membership.objects.values_list("user__username", "role"))


@pytest.mark.django_db(transaction=True)
def test_admin_members_become_secretaries_and_the_change_is_reversible():
    try:
        old = migrate(BEFORE)
        society = old.get_model("societies", "Society").objects.create(name="Old", slug="old")
        flat = old.get_model("societies", "Flat").objects.create(society=society, label="A-1")
        User = old.get_model("accounts", "User")
        Membership = old.get_model("societies", "Membership")
        for role in ("admin", "treasurer", "resident"):
            Membership.objects.create(
                society=society,
                user=User.objects.create(username=f"u-{role}"),
                role=role,
                flat=flat if role == "resident" else None,
            )

        forwards = roles_by_username(migrate(AFTER))
        assert forwards == {
            "u-admin": "secretary",
            "u-treasurer": "treasurer",
            "u-resident": "resident",
        }

        backwards = roles_by_username(migrate(BEFORE))
        assert backwards == {
            "u-admin": "admin",
            "u-treasurer": "treasurer",
            "u-resident": "resident",
        }
    finally:
        restore_database()


@pytest.mark.django_db(transaction=True)
def test_the_new_constraint_rejects_the_old_role_name_once_migrated():
    try:
        new = migrate(AFTER)
        society = new.get_model("societies", "Society").objects.create(name="New", slug="new")
        user = new.get_model("accounts", "User").objects.create(username="someone")
        Membership = new.get_model("societies", "Membership")

        with pytest.raises(IntegrityError), transaction.atomic():
            Membership.objects.create(society=society, user=user, role="admin")
        Membership.objects.create(society=society, user=user, role="president")  # allowed
    finally:
        restore_database()
