import os
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.billing.services import current_period, run_billing
from apps.expenses.services import record_expense
from apps.ledger.models import LedgerEntry
from apps.ledger.services import record_payment, reverse_entry
from apps.societies.models import Flat, Society
from apps.societies.services import add_member

D = Decimal

# (label, monthly maintenance) - two flats per floor, three floors, two blocks.
FLATS = [
    (f"{block}-{floor}0{n}", D(rent))
    for block in "AB"
    for floor, rent in ((1, "1500.00"), (2, "1800.00"), (3, "2200.00"))
    for n in (1, 2)
]

# username -> (role, flat label or None). Office-bearers are also residents: each lives in a
# flat of their own and pays dues like anyone else.
PEOPLE = {
    "vikram": ("president", "B-201"),
    "asha": ("secretary", "A-301"),
    "tara": ("treasurer", "A-302"),
    "ravi": ("resident", "A-101"),
    "meera": ("resident", "A-102"),
    "kiran": ("resident", "A-201"),
    "priya": ("resident", "A-202"),
    "john": ("resident", "B-101"),
    "nisha": ("resident", "B-102"),
}

# (category, description, amount, days ago)
EXPENSES = [
    ("salaries", "Security staff salaries", "12000.00", 3),
    ("utilities", "Common-area electricity", "6400.00", 5),
    ("repairs", "Lift servicing", "4500.00", 12),
    ("salaries", "Housekeeping salaries", "4000.00", 20),
    ("repairs", "CCTV camera repair", "2200.00", 28),
]


def previous_month(first_of_month):
    return (first_of_month - timedelta(days=1)).replace(day=1)


class Command(BaseCommand):
    help = (
        "Create a demo society with flats, a president, secretary, treasurer and residents "
        "(office-bearers live in flats too), three billed months, some payments and expenses. "
        "Built through the real services. Safe to re-run: does nothing if it already exists."
    )

    def add_arguments(self, parser):
        parser.add_argument("--slug", default="sunrise-heights", help="Society slug.")
        parser.add_argument(
            "--password",
            help="Password for every demo login (or set DEMO_PASSWORD). Never has a default.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        password = options["password"] or os.environ.get("DEMO_PASSWORD")
        if not password:
            raise CommandError("Pass --password or set DEMO_PASSWORD (demo logins need one).")

        slug = options["slug"]
        if Society.objects.filter(slug=slug).exists():
            self.stdout.write(f"{slug}: already seeded, nothing to do.")
            return

        society = Society.objects.create(name=slug.replace("-", " ").title(), slug=slug)
        flats = {
            label: Flat.objects.create(society=society, label=label, monthly_maintenance=rent)
            for label, rent in FLATS
        }

        users = {}
        for username, (role, flat_label) in PEOPLE.items():
            user, created = get_user_model().objects.get_or_create(username=username)
            if created:
                user.set_password(password)
                user.save()
            users[username] = user
            add_member(
                society=society,
                user=user,
                role=role,
                flat=flats[flat_label] if flat_label else None,
            )
        treasurer, secretary = users["tara"], users["asha"]
        lives_in = {label: name for name, (_, label) in PEOPLE.items() if label}

        def recorder_for(label):
            """Who records payments for a flat. The treasurer does, unless the treasurer lives
            there: nobody may record payments for their own flat, so the secretary does."""
            return secretary if lives_in.get(label) == "tara" else treasurer

        # Three months of billing: two previous months and the current one.
        this_month = current_period()
        last_month = previous_month(this_month)
        periods = [previous_month(last_month), last_month, this_month]
        for period in periods:
            run_billing(society=society, period=period)

        # Payment patterns so the dashboard shows a realistic spread.
        reversed_one, reversed_label = None, None
        for index, (label, rent) in enumerate(FLATS):
            flat = flats[label]
            pattern = index % 4
            if pattern == 3:
                continue  # pays nothing
            months_paid = (3, 2, 1)[pattern]
            for _ in range(months_paid):
                payment, _ = record_payment(
                    society=society,
                    flat=flat,
                    amount=rent,
                    actor=recorder_for(label),
                    note="Maintenance",
                )
                if index == 1:
                    reversed_one, reversed_label = payment, label
            if pattern == 2:
                # A partial payment on top of one full month: pays half of the next.
                record_payment(
                    society=society, flat=flat, amount=(rent / 2).quantize(D("0.01")),
                    actor=recorder_for(label), note="Part payment",
                )
        if reversed_one is not None:
            reverse_entry(
                society=society,
                entry=reversed_one,
                actor=recorder_for(reversed_label),
                note="Cheque bounced",
            )

        today = timezone.localdate()
        for category, description, amount, days_ago in EXPENSES:
            record_expense(
                society=society, actor=treasurer, category=category, description=description,
                amount=D(amount), paid_on=today - timedelta(days=days_ago),
            )

        self.stdout.write(
            f"Seeded '{slug}': {len(flats)} flats, {len(PEOPLE)} logins "
            f"({', '.join(PEOPLE)}), {len(periods)} billing months, "
            f"{LedgerEntry.objects.for_society(society).count()} ledger entries."
        )
