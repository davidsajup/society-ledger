from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.audit.models import AuditLog
from apps.billing.models import BillingRun
from apps.expenses.models import Expense
from apps.ledger.models import LedgerEntry
from apps.ledger.selectors import outstanding_for_flat
from apps.reports.selectors import society_summary
from apps.societies.models import Flat, Membership, Society

pytestmark = pytest.mark.django_db

PASSWORD = "throwaway-test-password"


def seed(*extra):
    out = StringIO()
    call_command("seed_demo", "--password", PASSWORD, *extra, stdout=out)
    return out.getvalue()


def test_seed_builds_a_realistic_society_through_the_real_services():
    output = seed()

    society = Society.objects.get(slug="sunrise-heights")
    assert Flat.objects.for_society(society).count() == 12
    roles = sorted(Membership.objects.for_society(society).values_list("role", flat=True))
    assert roles == ["admin"] + ["resident"] * 6 + ["treasurer"]
    assert BillingRun.objects.for_society(society).count() == 3
    assert Expense.objects.for_society(society).count() == 5
    # Built through the services, so the audit trail exists too.
    assert AuditLog.objects.for_society(society).filter(action="billing.run").count() == 3
    assert AuditLog.objects.for_society(society).filter(action="payment.recorded").exists()
    assert AuditLog.objects.for_society(society).filter(action="entry.reversed").count() == 1
    assert PASSWORD not in output  # the password is never echoed


def test_seeded_books_are_internally_consistent_and_varied():
    seed()
    society = Society.objects.get(slug="sunrise-heights")

    summary = society_summary(society)
    totals = summary["totals"]

    assert totals["billed"] - totals["collected"] == totals["outstanding"]
    assert totals["outstanding"] > Decimal("0")
    assert totals["spent"] > Decimal("0")
    balances = {outstanding_for_flat(f) for f in Flat.objects.for_society(society)}
    assert Decimal("0.00") in balances and len(balances) > 3  # paid up, partial and unpaid
    assert all(b >= 0 for b in balances)  # never overpaid
    for row in summary["flats"]:
        flat = Flat.objects.get(pk=row["id"])
        assert row["outstanding"] == outstanding_for_flat(flat)


def test_seed_logins_can_actually_log_in():
    from django.contrib.auth import authenticate

    seed()

    assert authenticate(username="tara", password=PASSWORD) is not None
    assert authenticate(username="tara", password="wrong") is None


def test_seed_is_idempotent():
    seed()
    entries, logs = LedgerEntry.objects.count(), AuditLog.objects.count()

    second = seed()

    assert "already seeded" in second
    assert (LedgerEntry.objects.count(), AuditLog.objects.count()) == (entries, logs)


def test_seed_refuses_to_run_without_a_password(monkeypatch):
    monkeypatch.delenv("DEMO_PASSWORD", raising=False)

    with pytest.raises(CommandError, match="password"):
        call_command("seed_demo")
    assert not Society.objects.exists()


def test_a_failed_seed_leaves_nothing_behind(monkeypatch):
    import apps.societies.management.commands.seed_demo as command

    def boom(**kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(command, "record_expense", boom)

    with pytest.raises(RuntimeError):
        seed()

    assert not Society.objects.exists()
    assert not LedgerEntry.objects.exists()
