from datetime import date

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.billing.services import current_period, run_billing
from apps.societies.models import Society


class Command(BaseCommand):
    help = "Bill societies for a cycle. Idempotent: cycles already billed are skipped."

    def add_arguments(self, parser):
        parser.add_argument(
            "--period",
            help="First month of the cycle, as YYYY-MM (default: each society's current cycle).",
        )
        parser.add_argument("--society", type=int, help="Only this society id (default: all).")

    def handle(self, *args, **options):
        if options["period"]:
            try:
                year, month = options["period"].split("-")
                period = date(int(year), int(month), 1)
            except ValueError as exc:
                raise CommandError("--period must look like 2026-11") from exc
        else:
            period = None

        societies = Society.objects.all()
        if options["society"]:
            societies = societies.filter(pk=options["society"])

        for society in societies:
            wanted = period or current_period(cycle_months=society.billing_cycle_months)
            try:
                run, created = run_billing(society=society, period=wanted)
            except ValidationError as exc:
                # e.g. 2026-11 for a quarterly society: say so and carry on with the others.
                self.stdout.write(f"{society.slug}: skipped ({'; '.join(exc.messages)})")
                continue
            state = "billed" if created else "already billed"
            self.stdout.write(
                f"{society.slug}: {state} {wanted:%Y-%m} "
                f"(flats={run.flats_charged}, total={run.total_amount})"
            )
