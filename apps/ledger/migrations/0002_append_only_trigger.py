from django.db import migrations

# Second line of defence behind the Python guard in models.py: Postgres itself refuses to
# change or delete a ledger row, whatever client or SQL tries it. (TRUNCATE does not fire row
# triggers; that is what lets the test runner flush tables between tests.)
CREATE = """
CREATE FUNCTION ledger_block_mutation() RETURNS trigger
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    RAISE EXCEPTION 'ledger_ledgerentry is append-only: % is not allowed', TG_OP
        USING ERRCODE = 'integrity_constraint_violation';
END;
$$;

CREATE TRIGGER ledger_entry_append_only
BEFORE UPDATE OR DELETE ON ledger_ledgerentry
FOR EACH ROW EXECUTE FUNCTION ledger_block_mutation();
"""

DROP = """
DROP TRIGGER IF EXISTS ledger_entry_append_only ON ledger_ledgerentry;
DROP FUNCTION IF EXISTS ledger_block_mutation();
"""


class Migration(migrations.Migration):
    dependencies = [("ledger", "0001_initial")]

    operations = [migrations.RunSQL(sql=CREATE, reverse_sql=DROP)]
