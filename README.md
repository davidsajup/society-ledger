# Society Ledger

A multi-tenant finance platform for housing societies. Each society has its own flats, residents and money, completely isolated from every other society. Residents see their dues and receipts, the treasurer records payments and expenses, and an append-only ledger plus an audit trail means nothing can be quietly changed.

**Stack:** Django + Django REST Framework, PostgreSQL (Supabase), Redis + Celery, React + TypeScript + Vite + Mantine, Docker Compose, pytest.

> Status: backend and frontend are built and tested locally. CI and deployment are the next milestone (see [PLAN.md](PLAN.md)).

## What it does

| Role | What they can do |
|---|---|
| **Super admin** | Creates societies and gives each one's president the first login. Belongs to no society and cannot see any money. |
| **Resident** | See their flat's balance, a statement with a running balance, and printable receipts (void if the payment was reversed). Only their own flat. Tap **I have paid** to tell the treasurer about a payment made outside the app; the treasurer checks it and records it, and the resident sees the answer. |
| **Treasurer** | See collected vs outstanding, record payments (with one-tap reversal), check and record the payments residents report (or turn them down with a reason), record expenses, see who is behind cycle by cycle, read the billing schedule, and review the audit trail. |
| **Secretary / President** | Everything the treasurer can do except expenses, plus managing flats, creating logins one by one or in bulk from a CSV/Excel sheet (with printable slips), issuing new temporary passwords and changing roles. The **president alone** sets how often the society is billed and when billing starts, until the first billing run. |

Office-bearers are residents too: each can have a flat and pays their own dues, shown as a "Your dues" card. Nobody can record or reverse a payment for the flat they live in; another office-bearer must.

Dues are generated automatically for every flat by a scheduled job, every month or every quarter depending on the society's billing schedule. Billing only adds a charge to each flat's ledger; it takes no money. Payments are recorded separately, and a flat can pay in installments.

## Guarantees, and where each one is tested

The point of this project is that these properties are enforced and *proven*, not assumed.

| Guarantee | How it is enforced | Proof |
|---|---|---|
| **Tenant isolation.** One society can never see or change another's data. | Every query goes through `for_society()`; the society comes from the URL and the caller must be a member; a non-member gets the same 404 as a missing id. | `apps/societies/tests/test_cross_tenant.py` attacks every route with every HTTP method as a secretary and a treasurer of another society, and a guard test fails if a new route has no coverage. |
| **No double-crediting.** Two payments at once cannot overpay a flat. | `select_for_update()` on the flat row; the balance is recomputed after the lock. | `apps/ledger/tests/test_payments.py`: 10 simultaneous payments against 100 owed, exactly 3 succeed. Removing the lock makes it fail. |
| **Retries are safe.** A double click or flaky network records one payment. | `Idempotency-Key` header with a unique constraint. | Parallel same-key tests (ledger and expenses). |
| **History cannot be rewritten.** | Ledger, expense and audit rows are append-only in Python **and** by a Postgres trigger that rejects `UPDATE`/`DELETE` even from raw SQL. Corrections are reversing entries. | `test_models.py`, `test_audit.py`, `test_expenses.py`. |
| **Billing runs exactly once per cycle** (month or quarter), even if the job runs twice, concurrently, or crashes halfway. It never runs before the society's start date, and the schedule cannot change once billing has started. | One transaction per society and cycle, guarded by `UNIQUE(society, period)`. The start date and the schedule change both go through one lock on the society row. | `apps/billing/tests/test_billing.py`: 10 simultaneous runs, a simulated crash, and re-runs. |
| **Every money action is audited atomically.** | The audit row is written in the same transaction as the change. | If the audit write fails, the payment (or the whole billing cycle) rolls back. |
| **Money is exact.** | `Decimal` everywhere, strings in JSON and in the browser, never floats. | Tests for exact cents; the UI never converts money to a JavaScript number. |
| **No self-dealing.** Nobody records or reverses a payment for their own flat, or changes their own role. | `refuse_own_flat` in the ledger service (checked before the lock, so nothing is written); `change_member` refuses self-change and keeps at least one manager under row locks. | `apps/ledger/tests/test_self_dealing.py`, `apps/societies/tests/test_change_role.py` |
| **A super admin cannot read a society's money.** | The platform role is a superuser flag with no membership; every society route is 404 for them. | `apps/onboarding/tests/` and the super-admin case in `test_cross_tenant.py` |
| **A bulk import is all-or-nothing and re-checked by the server.** | One transaction under a per-society lock; the confirm re-validates every row. | `apps/imports/tests/`: bad row, edited preview, double confirm, two imports at once |
| **Uploaded spreadsheets cannot hurt the server.** | Size/row limits, no formula evaluation, no macros, zip-bomb and XML-entity guards. | `apps/imports/tests/test_parsing.py` |
| **Admin-issued logins are safe.** | Random one-time passwords (never derived from the flat), changed at first login and enforced on the server, expiring if unused, with limited re-issue. | `apps/accounts/tests/test_credentials.py` |
| **Demo mode cannot be abused.** | Off by default, allowlisted users only, never staff or superusers. | `apps/accounts/tests/test_demo.py` |

The design reasoning, including what was rejected and why, is in [docs/decisions.md](docs/decisions.md) and the invariants are in [docs/domain-rules.md](docs/domain-rules.md).

## Quick start

You need Python 3.11+, a recent Node (developed on Node 25) and Docker.

```bash
# 1. Backend
python -m venv .venv
.venv/Scripts/activate            # Windows; macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env              # then fill it in (see below)
```

**Database.** The app is designed for PostgreSQL on Supabase: copy the **Session pooler** connection string (host `*.pooler.supabase.com`, port **5432**, not the transaction pooler) into `DATABASE_URL` in `.env`, and add `?sslmode=require`. To run entirely locally instead, start the bundled Postgres and point at it:

```bash
docker compose up -d db-test
# in .env:  DATABASE_URL=postgres://ledger:ledger@localhost:5433/ledger_test
```

Set `DJANGO_SECRET_KEY` to a long random value (`python -c "import secrets; print(secrets.token_urlsafe(50))"`). Never commit `.env`.

```bash
# 2. Create tables and demo data (pick your own password; it is not stored anywhere)
python manage.py migrate
python manage.py seed_demo --password "choose-a-password"

# 3. Run the API
python manage.py runserver

# 4. Run the UI (in a second terminal)
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 and log in as `vikram` (president), `asha` (secretary), `tara` (treasurer) or `ravi`, `meera`, `kiran`, `priya`, `john`, `nisha` (residents), with the password you chose.

**Billing** normally runs from Celery beat: every day at 01:00 India time it bills each society's current cycle (a month or a quarter), once the society's billing start date has arrived. The worker, beat and Redis must all be running for that. To run it by hand, or to run the worker:

```bash
python manage.py run_billing --period 2026-11        # idempotent: run it twice, it bills once
docker compose up -d redis
celery -A config worker -l info --pool=solo          # --pool=solo is needed on Windows
celery -A config beat -l info
```

`run_billing` refuses, with a message, to bill any cycle before a society's billing start date. A quarterly society only accepts the first day of January, April, July or October as `--period`.

### Demo mode (for visitors with no login)

Adds one-click role cards to the login page and a "Demo" strip inside the app. It is off unless enabled, and only works for the usernames you list. Add to `.env`, **only on a database that holds fake data**:

```bash
DEMO_MODE=True
DEMO_USERS=asha,tara,ravi,nisha
```

Django prints a warning on every start while it is on. A public demo should use its own database, reseeded regularly, because visitors can change the data.

### Admin-issued logins

Real users do not sign up; the president or secretary creates their login: **People → Add person → Create a login**. The app shows a username and a one-time temporary password **once**, to be handed over privately. The person must choose their own password at first login, and an unused temporary password expires after `TEMP_PASSWORD_DAYS` (default 7). They can issue a new one with **New password**.

## Tests

Tests run against a local Postgres container (never Supabase), because row locking and database triggers must be tested on the real thing.

```bash
docker compose up -d db-test
python -m pytest              # 888 tests
python -m ruff check .
cd frontend && npm run typecheck && npm run build
```

## Project layout

```
apps/
  societies/   tenants, flats, memberships, roles and permissions
  ledger/      append-only ledger, payments, reversals, idempotency
  billing/     billing runs (monthly or quarterly) and the Celery tasks
  expenses/    append-only expenses with reversals
  audit/       append-only audit log
  reports/     read-only summaries, dues by cycle, billing history
  accounts/    custom user, login, passwords, demo mode
  onboarding/  the super admin: creates societies and first presidents
  imports/     bulk upload of flats and people from CSV or Excel
  core/        shared tenancy, money and append-only machinery
config/        Django settings, URLs, Celery
frontend/      React + TypeScript app
docs/          decisions.md (why), domain-rules.md (invariants)
```

Business logic lives in `services.py` modules, not in views.

## Scope and known limitations

- **Payments are recorded by a person.** Money arrives outside the app (cash, UPI, bank transfer), so the treasurer records it. There is no online payment processing.
- **No self-sign-up or email.** Office-bearers create logins and hand over passwords, one by one or from an uploaded sheet with printable slips.
- **Not deployed yet, and not safe for residents over the internet.** There is no HTTPS or production server configuration. Run it on your own computer. See [docs/real-data.md](docs/real-data.md) for setting up a real society.
- **The frontend has no automated tests**, only strict TypeScript and manual checks.
- Lists are capped (200 rows); there is no pagination yet.
- Out of scope for now: complaints, social features, reminders, and AI features (receipt extraction, natural-language questions), which are planned for after the main build. See [PLAN.md](PLAN.md).

## Documentation

- [PLAN.md](PLAN.md): milestones, what is done, what is next.
- [docs/decisions.md](docs/decisions.md): 66 numbered decisions with what was chosen, what was rejected and why.
- [docs/domain-rules.md](docs/domain-rules.md): the rules the code must never break.
- [docs/real-data.md](docs/real-data.md): setting up a real society, step by step.
