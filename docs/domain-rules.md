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
- Recording a payment is a single atomic operation: lock the flat row (`select_for_update`), recompute what is owed, check, write the entry, write the audit row (M4), then commit.
- A payment may never exceed what the flat currently owes (no advance payments or credit). The same rule applies to reversals: a charge cannot be reversed while the flat has paid it.
- An entry is reversed at most once, and a reversal cannot itself be reversed.
- A retried payment carrying the same `Idempotency-Key` returns the original entry and records nothing new. The same key with a different request is a conflict (409).
- Residents may read only their own flat's ledger. Another flat in the same society is a 404, identical to a flat that does not exist.

## Billing
- Monthly billing for a `(society, period)` pair happens **exactly once**. A unique constraint on BillingRun enforces this, and the job is safe to run twice or concurrently.
- A billing run is one transaction: a month is fully billed or not billed at all, never half. Flats with `monthly_maintenance = 0` are not billed.
- Each flat gets at most one maintenance charge per period, also backed by a unique constraint.

## Audit
- Every money-changing action (payment, reversal, billing run, expense, expense reversal) writes an AuditLog row (actor, society, action, object, amount, timestamp) in the same transaction as the change. If either write fails, both roll back.
- Replays, already-billed months and rejected requests change nothing, so they write no audit row.
- AuditLog rows, like ledger entries and expenses, can never be updated or deleted (Python guard plus Postgres trigger). The audit log is read-only over HTTP.
- Expenses: positive `Decimal` amounts, not dated in the future; corrected only by a reversing expense (at most once; a reversal cannot be reversed); a retried request with the same `Idempotency-Key` returns the original.

## Logins
- A login is created by a society president or secretary, never by self-sign-up. The temporary password is random, shown once, stored only as a hash, and never written to logs, audit rows or list responses.
- A person on a temporary password can only reach `me`, `logout` and `change-password` until they choose their own password. The server enforces this on every request.
- An unused temporary password expires (default 7 days); after that even the correct password is refused until a manager re-issues it.
- Re-issuing is allowed only for a member of the manager's own society who belongs to no other society, and never for staff, superusers or the manager themselves. It ends the person's existing sessions and is audited without the password.
- Usernames include the society slug, so two societies' flats never collide.

## Roles (per society, via Membership)
One role per person per society. Office-bearers are also residents: a flat is **required** for a resident and **optional** for the other roles, so a president, secretary or treasurer can live in a flat and owe dues like anyone else.

| Action | President | Secretary | Treasurer | Resident |
|---|---|---|---|---|
| Manage flats, create logins, change roles | yes | yes | no | no |
| Record and reverse payments | yes | yes | yes | no |
| Record and reverse expenses | no | no | yes | no |
| View all flats' balances, expenses, society totals | yes | yes | yes | no |
| View audit log | yes | yes | yes | no |
| View own flat's dues, statement, receipts | yes | yes | yes | yes |

A user can belong to several societies, with one role in each.

## Segregation of duties
- **Nobody records or reverses a payment for a flat they live in**, whatever their role. Another office-bearer must do it (HTTP 403, nothing written). This also covers housemates who share a flat.
- **Nobody changes their own role or flat.** Another manager does it.
- **A society always keeps at least one member who can manage members.** Demoting the last one is refused; the managers are locked in a fixed order so two simultaneous demotions cannot both succeed.
