from datetime import date
from decimal import Decimal

import pytest
from django.db import IntegrityError, connection, transaction

from apps.audit import services as audit
from apps.audit.models import AuditLog
from apps.billing import services as billing_services
from apps.billing.models import BillingRun
from apps.billing.services import run_billing
from apps.core.append_only import AppendOnlyError
from apps.ledger import services as ledger_services
from apps.ledger.models import LedgerEntry
from apps.ledger.selectors import outstanding_for_flat
from apps.ledger.services import (
    PaymentExceedsOutstanding,
    record_payment,
    reverse_entry,
)
from apps.ledger.tests.helpers import build_world
from apps.societies.models import Flat

D = Decimal
NOV = date(2026, 11, 1)


def logs(action=None):
    qs = AuditLog.objects.all()
    return qs.filter(action=action) if action else qs


# --- Every money action leaves exactly one audit row -------------------------------------


@pytest.mark.django_db
def test_recording_a_payment_writes_one_audit_row_with_the_facts():
    society, flat, treasurer = build_world("100.00")

    entry, _ = record_payment(
        society=society, flat=flat, amount=D("30.00"), actor=treasurer, idempotency_key="k1"
    )

    row = logs().get()
    assert (row.action, row.actor, row.flat, row.society) == (
        "payment.recorded", treasurer, flat, society,
    )
    assert (row.object_type, row.object_id, row.amount) == ("ledger_entry", entry.pk, D("30.00"))
    assert row.data == {"idempotency_key": "k1"}


@pytest.mark.django_db
def test_an_idempotent_replay_writes_no_second_audit_row():
    society, flat, treasurer = build_world("100.00")
    kwargs = dict(
        society=society, flat=flat, amount=D("30.00"), actor=treasurer, idempotency_key="k1"
    )
    record_payment(**kwargs)
    record_payment(**kwargs)

    assert logs("payment.recorded").count() == 1


@pytest.mark.django_db
def test_a_rejected_payment_writes_no_audit_row():
    society, flat, treasurer = build_world("100.00")

    with pytest.raises(PaymentExceedsOutstanding):
        record_payment(society=society, flat=flat, amount=D("500.00"), actor=treasurer)

    assert not logs().exists()


@pytest.mark.django_db
def test_reversal_is_audited_with_what_it_reverses():
    society, flat, treasurer = build_world("100.00")
    payment, _ = record_payment(society=society, flat=flat, amount=D("40.00"), actor=treasurer)

    reversal = reverse_entry(society=society, entry=payment, actor=treasurer)

    row = logs("entry.reversed").get()
    assert (row.object_id, row.amount) == (reversal.pk, D("40.00"))
    assert row.data == {"reverses": payment.pk, "original_kind": "payment"}


@pytest.mark.django_db
def test_billing_is_audited_as_a_system_action_and_replays_add_nothing():
    society = build_world(owed=None)[0]
    Flat.objects.create(society=society, label="A-2", monthly_maintenance=D("1500.00"))
    Flat.objects.create(society=society, label="A-3", monthly_maintenance=D("500.50"))

    run_billing(society=society, period=NOV)
    run_billing(society=society, period=NOV)

    row = logs("billing.run").get()
    assert row.actor is None
    assert (row.amount, row.data) == (D("2000.50"), {"period": "2026-11", "flats_charged": 2})


# --- Atomicity: the audit row and the money move together ---------------------------------


@pytest.mark.django_db(transaction=True)
def test_if_the_audit_write_fails_the_payment_is_rolled_back(monkeypatch):
    """Proves: no payment without its audit row. A failure writing the audit undoes the money."""
    society, flat, treasurer = build_world("100.00")

    def broken(**kwargs):
        raise RuntimeError("audit store down")

    monkeypatch.setattr(ledger_services.audit, "record", broken)

    with pytest.raises(RuntimeError):
        record_payment(society=society, flat=flat, amount=D("30.00"), actor=treasurer)

    assert LedgerEntry.objects.filter(kind="payment").count() == 0
    assert outstanding_for_flat(flat) == D("100.00")


@pytest.mark.django_db(transaction=True)
def test_if_the_audit_write_fails_the_whole_billing_month_is_rolled_back(monkeypatch):
    society = build_world(owed=None)[0]
    Flat.objects.create(society=society, label="A-2", monthly_maintenance=D("1500.00"))

    def broken(**kwargs):
        raise RuntimeError("audit store down")

    monkeypatch.setattr(billing_services.audit, "record", broken)

    with pytest.raises(RuntimeError):
        run_billing(society=society, period=NOV)

    assert BillingRun.objects.count() == 0
    assert LedgerEntry.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_audit_record_refuses_to_run_outside_a_transaction():
    society = build_world(owed=None)[0]
    assert not connection.in_atomic_block

    with pytest.raises(RuntimeError, match="inside transaction.atomic"):
        audit.record(
            society=society, action=AuditLog.Action.PAYMENT_RECORDED, object_type="x", object_id=1
        )


# --- Append-only ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_audit_rows_cannot_be_changed_or_deleted_through_the_orm():
    society, flat, treasurer = build_world("100.00")
    record_payment(society=society, flat=flat, amount=D("10.00"), actor=treasurer)
    row = logs().get()

    row.amount = D("1.00")
    with pytest.raises(AppendOnlyError):
        row.save()
    with pytest.raises(AppendOnlyError):
        row.delete()
    with pytest.raises(AppendOnlyError):
        AuditLog.objects.all().update(amount=D("1.00"))
    with pytest.raises(AppendOnlyError):
        AuditLog.objects.all().delete()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "sql", ["UPDATE audit_auditlog SET amount = 1", "DELETE FROM audit_auditlog"]
)
def test_audit_rows_cannot_be_changed_or_deleted_with_raw_sql(sql):
    society, flat, treasurer = build_world("100.00")
    record_payment(society=society, flat=flat, amount=D("10.00"), actor=treasurer)

    with pytest.raises(IntegrityError, match="append-only"), transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(sql)
    assert logs().count() == 1
