from datetime import date

from django.core.management.base import BaseCommand, CommandError

from apps.billing.services import current_period, run_billing
from apps.societies.models import Society


class Command(BaseCommand):
    help = "Bill societies for a month. Idempotent: months already billed are skipped."

    def add_arguments(self, parser):
        parser.add_argument("--period", help="Month to bill as YYYY-MM (default: this month).")
        parser.add_argument("--society", type=int, help="Only this society id (default: all).")

    def handle(self, *args, **options):
        if options["period"]:
            try:
                year, month = options["period"].split("-")
                period = date(int(year), int(month), 1)
            except ValueError as exc:
                raise CommandError("--period must look like 2026-11") from exc
        else:
            period = current_period()

        societies = Society.objects.all()
        if options["society"]:
            societies = societies.filter(pk=options["society"])

        for society in societies:
            run, created = run_billing(society=society, period=period)
            state = "billed" if created else "already billed"
            self.stdout.write(
                f"{society.slug}: {state} {period:%Y-%m} "
                f"(flats={run.flats_charged}, total={run.total_amount})"
            )
