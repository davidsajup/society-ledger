from django.conf import settings
from django.db import migrations, models


def admin_to_secretary(apps, schema_editor):
    """The old 'admin' role becomes 'secretary' (same powers: they ran the society's setup)."""
    Membership = apps.get_model("societies", "Membership")
    Membership.objects.filter(role="admin").update(role="secretary")


def secretary_to_admin(apps, schema_editor):
    """Reverse. Lossy by nature: 'admin' did not distinguish president from secretary."""
    Membership = apps.get_model("societies", "Membership")
    Membership.objects.filter(role__in=["president", "secretary"]).update(role="admin")


class Migration(migrations.Migration):
    dependencies = [
        ("societies", "0003_flat_monthly_maintenance_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    # The ORDER matters: the old CHECK would reject the new role names, and the new CHECK would
    # reject leftover 'admin' rows, so the data is converted while NO role CHECK exists.
    operations = [
        migrations.RemoveConstraint(model_name="membership", name="membership_role_valid"),
        migrations.AlterField(
            model_name="membership",
            name="role",
            field=models.CharField(
                choices=[
                    ("president", "President"),
                    ("secretary", "Secretary"),
                    ("treasurer", "Treasurer"),
                    ("resident", "Resident"),
                ],
                max_length=20,
            ),
        ),
        migrations.RunPython(admin_to_secretary, secretary_to_admin),
        migrations.AddConstraint(
            model_name="membership",
            constraint=models.CheckConstraint(
                condition=models.Q(("role__in", ["president", "secretary", "treasurer", "resident"])),
                name="membership_role_valid",
            ),
        ),
    ]
