# Decisions

Format: what we chose, what we rejected, why. Newest at the bottom.

## 001 — Django + DRF for the backend (2026-10-20)
- **Chose:** Django 5.2 LTS + Django REST Framework.
- **Rejected:** FastAPI for now.
- **Why:** The Django ORM gives `transaction.atomic`, `select_for_update` and migrations out of the box, and DRF has permission classes and object-level permissions built in. Those are the concepts this project exists to teach. I already use Django at work, so less time goes into plumbing. 5.2 is the LTS release.

## 002 — Supabase is used as managed Postgres only (2026-10-20)
- **Chose:** Supabase-hosted PostgreSQL for dev and prod, and later Supabase Storage for receipt files.
- **Rejected:**
  - **Supabase Auth.** It would mean two user stores (`auth.users` and Django `User`), a custom DRF class to verify Supabase JWTs, and sync code. Its strengths (social login, magic links) are out of scope.
  - **RLS as the primary tenant isolation.** Django connects as one database role, so RLS needs a per-request session variable to work, which is easy to get subtly wrong. It may come later as defense in depth.
  - **pg_cron / Edge Functions for billing.** Idempotent Celery billing is a core guarantee the project has to demonstrate.
  - **The auto-generated REST API.** It would bypass the backend entirely.
- **Why:** This keeps the learning focus (permissions, tenancy, ledger, Celery) in code I write and can explain, while still getting a managed database.

## 003 — Connect through the Supabase session pooler (2026-10-20)
- **Chose:** The session pooler (`*.pooler.supabase.com:5432`) with `sslmode=require`.
- **Rejected:**
  - **Direct host.** On the free tier it's IPv6-only, and Docker on Windows usually has no IPv6.
  - **Transaction pooler (6543).** It breaks Django's server-side cursors and prepared statements and makes row-lock behaviour harder to reason about.

## 004 — Tests run on a local Postgres container (2026-10-20)
- **Chose:** A `db-test` service (postgres:16) in docker-compose, and a separate `config/settings_test.py`.
- **Rejected:** Running tests against Supabase, or against SQLite.
- **Why:** pytest-django creates and drops a test database, which shouldn't happen on a hosted project and is slow over the network. SQLite ignores `select_for_update`, so concurrency tests would pass for the wrong reason. CI will use the same setup.

## 005 — pip + requirements files (2026-10-20)
- **Chose:** `requirements.txt` / `requirements-dev.txt` with pinned versions.
- **Rejected:** uv and poetry.
- **Why:** These are the simplest tools with nothing new to learn. Switching later is cheap.

## 006 — Hybrid dev setup: venv for code, Docker for infrastructure (2026-10-20)
- **Chose:** Run Django, pytest and ruff from a local `.venv`. Docker runs only `db-test` (Postgres on localhost:5433) and, from M3, Redis. The `web` service and Dockerfile stay for building the production image.
- **Rejected:** Running the Django server inside Docker during development.
- **Why:** Commands start in about a second and run dozens of times per weekend. Breakpoints, tracebacks and editor imports work without container setup. Docker is used where it adds value: disposable services and the deploy image. The Dockerfile uses Python 3.11 to match the local venv.
- **Watch out:** Tests and dev use different databases, so run `migrate` against Supabase after each new migration to catch problems tests can't.
