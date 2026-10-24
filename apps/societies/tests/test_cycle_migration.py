"""Migration 0005 renamed Flat.monthly_maintenance to maintenance_amount and added the cycle.

It will run against a live database, so it is rehearsed on real rows: every amount must survive
the rename in both directions, and existing societies must stay monthly with no start date.
"""

from decimal import Decimal

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

BEFORE = [("societies", "0004_office_bearer_roles")]
AFTER = [("societies", "0005_billing_cycle_and_amount_rename")]
ACCOUNTS = [("accounts", "0002_user_must_change_password_and_more")]


def migrate(targets):
    executor = MigrationExecutor(connection)
    executor.migrate(targets)
    return MigrationExecutor(connection).loader.project_state(targets + ACCOUNTS).apps


def restore_database():
    executor = MigrationExecutor(connection)
    executor.migrate(executor.loader.graph.leaf_nodes())


@pytest.mark.django_db(transaction=True)
def test_amounts_survive_the_rename_both_ways_and_old_societies_stay_monthly():
    try:
        old = migrate(BEFORE)
        society = old.get_model("societies", "Society").objects.create(name="Old", slug="old")
        old.get_model("societies", "Flat").objects.create(
            society=society, label="A-1", monthly_maintenance=Decimal("1500.00")
        )
        old.get_model("societies", "Flat").objects.create(
            society=society, label="A-2", monthly_maintenance=Decimal("1800.50")
        )

        new = migrate(AFTER)
        flats = new.get_model("societies", "Flat").objects
        amounts = dict(flats.values_list("label", "maintenance_amount"))
        assert amounts == {"A-1": Decimal("1500.00"), "A-2": Decimal("1800.50")}
        migrated = new.get_model("societies", "Society").objects.get(slug="old")
        assert migrated.billing_cycle_months == 1  # existing societies keep billing monthly
        assert migrated.billing_start is None  # and keep billing without a start restriction

        back = migrate(BEFORE)
        flats = back.get_model("societies", "Flat").objects
        names = dict(flats.values_list("label", "monthly_maintenance"))
        assert names == {"A-1": Decimal("1500.00"), "A-2": Decimal("1800.50")}
    finally:
        restore_database()
