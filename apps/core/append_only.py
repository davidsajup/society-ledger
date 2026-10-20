"""Shared machinery for tables whose rows must never change: ledger, expenses, audit log.

Two independent layers, so one bug cannot undo the guarantee:
  1. Python: AppendOnlyModel / AppendOnlyQuerySet refuse updates and deletes.
  2. Postgres: append_only_trigger() adds a trigger that refuses UPDATE and DELETE from any
     client, including raw SQL. (TRUNCATE does not fire row triggers, which is what lets the
     test runner flush tables between tests.)
"""

from django.db import migrations, models

from .tenancy import TenantQuerySet


class AppendOnlyError(Exception):
    """Raised on any attempt to change or delete an append-only row."""


class AppendOnlyQuerySet(TenantQuerySet):
    """Blocks bulk changes. bulk_update() goes through update(), so it is blocked too."""

    def update(self, **kwargs):
        raise AppendOnlyError("Rows in this table cannot be updated.")

    def delete(self):
        raise AppendOnlyError("Rows in this table cannot be deleted.")


class AppendOnlyModel(models.Model):
    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise AppendOnlyError("Rows in this table cannot be updated.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise AppendOnlyError("Rows in this table cannot be deleted.")


def append_only_trigger(table):
    """A RunSQL migration operation that makes `table` refuse UPDATE and DELETE."""
    function = f"{table}_block_mutation"
    create = f"""
    CREATE FUNCTION {function}() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path = ''
    AS $$
    BEGIN
        RAISE EXCEPTION '{table} is append-only: % is not allowed', TG_OP
            USING ERRCODE = 'integrity_constraint_violation';
    END;
    $$;

    CREATE TRIGGER {table}_append_only
    BEFORE UPDATE OR DELETE ON {table}
    FOR EACH ROW EXECUTE FUNCTION {function}();
    """
    drop = f"""
    DROP TRIGGER IF EXISTS {table}_append_only ON {table};
    DROP FUNCTION IF EXISTS {function}();
    """
    return migrations.RunSQL(sql=create, reverse_sql=drop)
