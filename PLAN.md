# Plan

**Current task:** verify and consolidate. New features are paused: everything listed below is built, tested (1,170 backend tests) and checked against Supabase. The next work is CI and deployment (M5), then rehearsing how to explain the ledger, the race tests and the decisions.

**Before the real society goes in:** the society on Supabase is a rehearsal (it already has a billing run, payments and a claim, which can never be removed), so the real one is created as a **new** society with its own start date. Still needed for go-live: HTTPS and a production setup (M5); something to run the daily billing job (Celery worker and beat), or run `manage.py run_billing` by hand on the start date; SMTP settings in the environment if reminder emails should really send. Follow [docs/real-data.md](docs/real-data.md).

**Built since the roles work:** super admin and `/platform` page; quarterly billing with `billing_start` (and `run_billing` refusing any cycle before it); bulk import of flats and people from CSV/Excel with preview, confirm and printable slips; phone and email per membership; the president decides the billing cycle and start date until billing starts (secretary and treasurer can read it); a duplicate-payment warning (same amount on the same flat within 10 minutes needs a deliberate yes); residents report payments ("I have paid") and office-bearers check and record or reject them; a "Remind flats that owe" email button (outbox, 7-day cooldown, counts only). Decisions 059-072 record why.

**Next demo step (M5):** a PUBLIC demo needs its own database that is reseeded regularly, and `DEMO_MODE` set only there.

**On hold:** M5 — GitHub Actions CI + deployment. Resume afterwards: CI workflow, production image, Render + Supabase prod project, and the cross-site cookie decision (040).

**Done:** M0 bootstrap; M1 tenancy (capability roles, tenant-scoped endpoints, session login, cross-tenant suite); M2 ledger (append-only LedgerEntry with DB trigger, `record_payment` with row lock + idempotency, reversals, object-level permissions); M3 billing (BillingRun unique per society+period, one-transaction idempotent `run_billing`, Celery + beat daily fan-out, Redis); M4 (append-only Expense with reversals, AuditLog written inside every money transaction); reports (summary, activity, dues by month, billing runs) and `seed_demo`; frontend: login, resident dashboard, treasurer overview/payments/expenses, people & roles (president, secretary, treasurer, resident; office-bearers have flats and cannot record their own flat's payments), plus flat statements with running balance, printable receipts (void if reversed), dues-by-month grid, an activity timeline with billing history, a demo mode (one-click role logins, off by default, with a banner), and admin-issued logins (random one-time passwords, forced change at first login, 7-day expiry, re-issue).

Budget: ~10 h/week on this project. Job applications start early February 2027 (~15 weekends from 2026-10-20).
Rule: backend milestones (M1–M5) are protected. If we slip, M6 (frontend) shrinks first.

| # | Weeks | Milestone | Done when this test/proof exists |
|---|---|---|---|
| M0 | 1 | Bootstrap: Docker, Django + DRF, Supabase connection, pytest, docs | Health check hits Supabase; `pytest` green on local db-test |
| M1 | 2–3 | Society, Flat, Membership (role), DRF auth, tenant-scoped querysets + permissions | Cross-tenant access test: user of society A gets 404 on society B's objects |
| M2 | 4–6 | Append-only LedgerEntry, Decimal money, `record_payment` service (`transaction.atomic` + `select_for_update`) | Parallel-payments test: N concurrent requests, no double credit |
| M3 | 7–8 | Redis + Celery beat billing (monthly or quarterly per society), idempotent via unique (society, period) BillingRun | Billing-run-twice test: second run creates zero charges |
| M4 | 9 | Expenses + AuditLog for every money action | Audit row is written in the same transaction (rollback test) |
| M5 | 10 | GitHub Actions CI (Postgres service) + deploy (Render + Supabase prod project) | Green CI badge, live URL |
| M6 | 11–14 | React + TS frontend: resident dashboard, treasurer dashboard, admin page | Usable demo on phone width |
| M7 | 15 | README, architecture diagram, decisions cleanup | Portfolio-ready repo |
| Later | — | Receipts and bank reconciliation (see the section below), optional RLS hardening, AI finance Q&A | — |

## After M5: receipts and bank reconciliation (planned; phase 1 partly built)

**Status:** the payment-claims part of phase 1 is built (decision 071): a resident reports a payment, an office-bearer accepts or rejects it, and accepting goes through `record_payment`. It differs from the plan below in two ways: there is no receipt upload yet, and the ledger key is `claim-<id>` rather than a bank reference. Receipt upload, AI pre-fill and statement import are still to do.

**Why:** today the treasurer types every payment. Uploaded receipts and a bank statement can remove most of that typing and attach evidence to each payment. A payment is still only recorded once the treasurer confirms it.

**Hard rules for every phase (decided, do not relax without discussing):**
1. A receipt creates a **claim**, never a payment. Only the treasurer's confirmation records money.
2. Confirmation goes through the existing `record_payment`, with the **bank/UPI reference as the idempotency key**. `UNIQUE(society, reference)` stops the same transfer being claimed twice.
3. **AI output is a suggestion.** Extracted fields are editable and are never recorded automatically.
4. **Privacy:** receipts live in a private Supabase Storage bucket, with the society id in the path and short-lived signed URLs. API keys live only in environment variables, never in files or chat. Receipts contain personal data, so sending them to a third-party model must be disclosed.
5. **Bank statements are never stored or sent anywhere.** The file is parsed in the browser; only `reference, amount, date` of credit rows go to the server; matching is plain code (no AI); unmatched rows are counted and discarded.
6. Ask before adding any dependency (S3 client, Anthropic SDK, CSV parser).

| Phase | What | Effort | Done when this test/proof exists |
|---|---|---|---|
| 1 | **Payment claims + receipt upload (no AI).** Resident taps "I paid", uploads a receipt and the amount. Treasurer sees a Pending list and confirms or rejects. Audit entries for both. | ~1 weekend | A claim cannot be confirmed twice; the same reference cannot be claimed twice; a resident cannot see another flat's claim or file; society A can never open society B's receipt |
| 2 | **AI pre-fill.** A vision model reads the receipt and suggests amount, date and reference; the treasurer edits and confirms. Falls back to manual entry if extraction fails. | ~1 weekend | Extraction is mocked in tests; a wrong suggestion never reaches the ledger without confirmation |
| 3 | **Statement import.** Treasurer picks a CSV, maps the columns once, previews matches (match / amount differs / no claim / still pending), then confirms in one click. Writes one audit entry ("statement imported: N rows, M matched") and nothing else from the file. | ~1-2 weekends | Importing the same statement twice records nothing the second time; another society's claims never match; the audit entry and logs contain no row data |

**Matching rule (phase 3):** a row matches a claim only if the reference is equal and the amount is exactly equal (decimal compare), within the same society's pending claims. A reference seen twice in one file is flagged, not double counted.

**Out of scope:** online payment gateway and webhooks, PDF or Excel statements, automatic (scheduled) reminders. The on-demand reminder email button is built (decision 072).

## M0 checklist
- [x] Project docs (CLAUDE.md, PLAN.md, domain rules, decisions)
- [x] Django + DRF skeleton, settings from env
- [x] Docker Compose: `web` + `db-test`
- [x] Health endpoint + test
- [x] You: create Supabase project, put session-pooler URL in `.env`, run migrate, hit `/api/health/`
