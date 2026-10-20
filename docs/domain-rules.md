# Domain rules

These are invariants. Code that breaks one of them is a bug, even if no test catches it yet.

## Tenancy
- A **Society** is the tenant. Every tenant-owned row (Flat, Membership, LedgerEntry, Expense, BillingRun, AuditLog) has a non-null `society_id`.
- No queryset that returns tenant-owned data reaches the database without a society filter. Views get their society from the authenticated user's membership, **never** from a client-supplied ID alone.
- Accessing another society's object returns **404**, not 403, so that IDs from other tenants don't leak.
- Each test suite includes a cross-tenant test for every new endpoint.

## Money
- Money is `DecimalField(max_digits=12, decimal_places=2)` in models and `Decimal` in Python. Floats never touch money, including in serializers (`coerce_to_string` stays on) and tests.
- Amounts on ledger entries are positive. The **entry type** gives the direction (charge or payment).
- Currency: a single currency per society (INR) for now. There is no conversion.

## Ledger
- Ledger entries are **append-only**. Nothing updates or deletes them. A mistake is fixed with a reversing entry that references the original.
- A flat's balance is `sum(charges) - sum(payments)`, derived from the ledger. Any cached balance is updated **in the same transaction** as the entry, under a row lock.
- Recording a payment is a single atomic operation: lock the flat row (`select_for_update`), write the entry, write the audit row, then commit.

## Billing
- Monthly billing for a `(society, period)` pair happens **exactly once**. A unique constraint on BillingRun enforces this, and the job is safe to run twice or concurrently.
- Each flat gets at most one maintenance charge per period, also backed by a unique constraint.

## Audit
- Every money-changing action writes an AuditLog row (actor, society, action, object, amount, timestamp) in the same transaction as the change.

## Roles (per society, via Membership)
| Action | Admin | Treasurer | Resident |
|---|---|---|---|
| Manage flats and residents | ✅ | ❌ | ❌ |
| Record payments and expenses | ❌ | ✅ | ❌ |
| View all flats' balances and society totals | ✅ | ✅ | ❌ |
| View own flat's dues and history | ✅ | ✅ | ✅ (own flat only) |
| View audit log | ✅ | ✅ | ❌ |

A user can belong to several societies, with one role in each.
