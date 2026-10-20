from django.db import migrations

from apps.core.append_only import append_only_trigger


class Migration(migrations.Migration):
    dependencies = [("expenses", "0001_initial")]

    operations = [append_only_trigger("expenses_expense")]
