# Society Ledger

A multi-tenant finance platform for housing societies. Each society has its own flats, residents and money, completely isolated from every other society. Residents see their dues and receipts, the treasurer records payments and expenses, and an append-only ledger plus an audit trail means nothing can be quietly changed.

**Stack:** Django + Django REST Framework, PostgreSQL (Supabase), Redis + Celery, React + TypeScript + Vite + Mantine, Docker Compose, pytest.

> Status: backend and frontend are built and tested locally. CI and deployment are the next milestone (see [PLAN.md](PLAN.md)).

## What it does

| Role | What they can do |
|---|---|
| **Resident** | See their flat's balance, a statement with a running balance, and printable receipts (void if the payment was reversed). Only their own flat. |
| **Treasurer** | See collected vs outstanding, record payments (with one-tap reversal), record expenses, see who is behind month by month, and review the audit trail. |
| **Admin** | Manage flats and their monthly amounts, create logins for residents, issue new temporary passwords, and review the books. |

Monthly dues are generated automatically for every flat by a scheduled job.

## Guarantees, and where each one is tested

The point of this project is that these properties are enforced and *proven*, not assumed.

| Guarantee | How it is enforced | Proof |
|---|---|---|
| **Tenant isolation.** One society can never see or change another's data. | Every query goes through `for_society()`; the society comes from the URL and the caller must be a member; a non-member gets the same 404 as a missing id. | `apps/societies/tests/test_cross_tenant.py` attacks every route with every HTTP method as an admin and a treasurer of another society, and a guard test fails if a new route has no coverage. |
| **No double-crediting.** Two payments at once cannot overpay a flat. | `select_for_update()` on the flat row; the balance is recomputed after the lock. | `apps/ledger/tests/test_payments.py`: 10 simultaneous payments against 100 owed, exactly 3 succeed. Removing the lock makes it fail. |
| **Retries are safe.** A double click or flaky network records one payment. | `Idempotency-Key` header with a unique constraint. | Parallel same-key tests (ledger and expenses). |
| **History cannot be rewritten.** | Ledger, expense and audit rows are append-only in Python **and** by a Postgres trigger that rejects `UPDATE`/`DELETE` even from raw SQL. Corrections are reversing entries. | `test_models.py`, `test_audit.py`, `test_expenses.py`. |
| **Billing runs exactly once per month**, even if the job runs twice, concurrently, or crashes halfway. | One transaction per society and month, guarded by `UNIQUE(society, period)`. | `apps/billing/tests/test_billing.py`: 10 simultaneous runs, a simulated crash, and re-runs. |
| **Every money action is audited atomically.** | The audit row is written in the same transaction as the change. | If the audit write fails, the payment (or the whole billing month) rolls back. |
| **Money is exact.** | `Decimal` everywhere, strings in JSON and in the browser, never floats. | Tests for exact cents; the UI never converts money to a JavaScript number. |
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

Open http://localhost:5173 and log in as `asha` (admin), `tara` (treasurer) or `ravi`, `meera`, `kiran`, `priya`, `john`, `nisha` (residents), with the password you chose.

**Monthly billing** normally runs from Celery beat. To try it by hand, or to run the worker:

```bash
python manage.py run_billing --period 2026-11        # idempotent: run it twice, it bills once
docker compose up -d redis
celery -A config worker -l info --pool=solo          # --pool=solo is needed on Windows
celery -A config beat -l info
```

### Demo mode (for visitors with no login)

Adds one-click role cards to the login page and a "Demo" strip inside the app. It is off unless enabled, and only works for the usernames you list. Add to `.env`, **only on a database that holds fake data**:

```bash
DEMO_MODE=True
DEMO_USERS=asha,tara,ravi,nisha
```

Django prints a warning on every start while it is on. A public demo should use its own database, reseeded regularly, because visitors can change the data.

### Admin-issued logins

Real users do not sign up; an admin creates their login: **Residents → Add person → Create a login**. The app shows a username and a one-time temporary password **once**, to be handed over privately. The person must choose their own password at first login, and an unused temporary password expires after `TEMP_PASSWORD_DAYS` (default 7). The admin can issue a new one with **New password**.

## Tests

Tests run against a local Postgres container (never Supabase), because row locking and database triggers must be tested on the real thing.

```bash
docker compose up -d db-test
python -m pytest              # 479 tests
python -m ruff check .
cd frontend && npm run typecheck && npm run build
```

## Project layout

```
apps/
  societies/   tenants, flats, memberships, roles and permissions
  ledger/      append-only ledger, payments, reversals, idempotency
  billing/     monthly billing runs and the Celery tasks
  expenses/    append-only expenses with reversals
  audit/       append-only audit log
  reports/     read-only summaries, dues by month, billing history
  accounts/    custom user, login, passwords, demo mode
  core/        shared tenancy, money and append-only machinery
config/        Django settings, URLs, Celery
frontend/      React + TypeScript app
docs/          decisions.md (why), domain-rules.md (invariants)
```

Business logic lives in `services.py` modules, not in views.

## Scope and known limitations

- **Payments are recorded by a person.** Money arrives outside the app (cash, UPI, bank transfer), so the treasurer records it. There is no online payment processing.
- **No self-sign-up or email.** Admins create logins and hand over passwords. CSV import and printable credential slips are planned.
- **Not deployed yet.** CI and a hosted demo are the next milestone.
- **The frontend has no automated tests**, only strict TypeScript and manual checks.
- Lists are capped (200 rows); there is no pagination yet.
- Out of scope for now: complaints, social features, reminders, and AI features (receipt extraction, natural-language questions), which are planned for after the main build. See [PLAN.md](PLAN.md).

## Documentation

- [PLAN.md](PLAN.md): milestones, what is done, what is next.
- [docs/decisions.md](docs/decisions.md): 53 numbered decisions with what was chosen, what was rejected and why.
- [docs/domain-rules.md](docs/domain-rules.md): the rules the code must never break.
