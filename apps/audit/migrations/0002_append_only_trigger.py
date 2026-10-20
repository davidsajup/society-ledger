from django.db import migrations

from apps.core.append_only import append_only_trigger


class Migration(migrations.Migration):
    dependencies = [("audit", "0001_initial")]

    operations = [append_only_trigger("audit_auditlog")]
