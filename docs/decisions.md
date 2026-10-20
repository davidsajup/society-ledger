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

## 007 — RLS on with no policies, Data API off; tenant policies deferred (2026-10-20)
- **Status:** decided, NOT yet implemented. To do: turn off the Data API in the Supabase dashboard, and add a helper that enables RLS on every table Django creates.
- **Chose:** Treat RLS as a deny-all safety net. Supabase exposes every `public` table through its auto-generated REST API, protected only by the public `anon` key. Django connects as `postgres`, which bypasses RLS, so enabling RLS with no policies blocks `anon` and `authenticated` and changes nothing for the app.
- **Rejected:** RLS as the primary tenant isolation. Django uses one database role, so policies would need a per-request `SET LOCAL app.society_id`, which is easy to get subtly wrong with connection pooling. Real tenant policies may come after M4 as defense in depth.
- **Why:** Tenant isolation stays in code I can explain and test (decisions 009, 012, 019). RLS only closes the hole the Supabase API would otherwise open.

## 008 — Custom User model from day one (2026-10-20)
- **Chose:** An empty `AbstractUser` subclass (`accounts.User`) set as `AUTH_USER_MODEL`. The Supabase tables created by the default User were dropped once, before any real data existed.
- **Rejected:** Django's default `auth.User`.
- **Why:** Swapping the user model after the first migration is painful. A user's role is deliberately not on User; it lives on Membership, because one person can belong to several societies with a different role in each.

## 009 — Society id in the URL, not a header (2026-10-20)
- **Chose:** `/api/societies/<society_id>/...`.
- **Rejected:** An `X-Society-ID` header.
- **Why:** Every route visibly belongs to a tenant, tests are simple, and a forgotten header can't silently pick the wrong tenant. The id from the URL is never trusted on its own: the caller must have a Membership in exactly that society (decision 012).

## 010 — Membership with database constraints (2026-10-20)
- **Chose:** `Membership(user, society, role, flat)` with `UNIQUE(user, society)` and `CHECK(role = 'resident' -> flat IS NOT NULL)`. Flat labels are `UNIQUE(society, label)`. `on_delete=PROTECT` on society and flat.
- **Rejected:** Rules only in Python; a role column on User; `CASCADE` or `SET_NULL` on flat.
- **Why:** Constraints hold even when code is bypassed (shell, future bugs). `PROTECT` stops a deletion from silently orphaning a resident or, later, ledger history.
- **Gap, enforced elsewhere:** the DB cannot check that a membership's flat is in the same society (Django has no composite foreign keys). `services.add_member` enforces it, the member serializer only accepts this society's flats, and tests cover both.

## 011 — Capability map instead of role checks in views (2026-10-20)
- **Chose:** `ROLE_PERMISSIONS` in `roles.py` maps each role to a set of capabilities. Views ask "can this membership do X?", never "is this a treasurer?".
- **Rejected:** `if role == "treasurer"` scattered through views; a database-driven roles and permissions system.
- **Why:** Adding a role is one dictionary entry with no view changes, and the table is easy to test. A DB-driven system would cost weeks for no current need, and the map is the interface it would later replace.

## 012 — 404 for non-members, 403 for under-privileged members (2026-10-20)
- **Chose:** `IsSocietyMember` returns 404 when the caller has no membership in the URL's society, identical to a society that doesn't exist. `HasCapability` returns 403 for members whose role lacks the capability.
- **Rejected:** 403 for non-members.
- **Why:** 403 would confirm which societies and object ids exist, which allows enumeration. A member already knows their society exists, so 403 reveals nothing new.

## 013 — Role values enforced by a database CHECK as well as Django choices (2026-10-20)
- **Chose:** `CHECK(role IN ('admin','treasurer','resident'))`, plus a test that every declared `Role` value is accepted.
- **Rejected:** Relying on `choices` alone.
- **Why:** `choices` is only validated by Django forms and serializers, so a raw insert could store any string. The constraint hardcodes the names because `Role` is not in scope inside `Meta`; the drift test fails if the enum and constraint disagree.

## 014 — Tenant comes from the URL, never from the request body (2026-10-20)
- **Chose:** Serializers have no `society` field; views inject `request.society` on save.
- **Rejected:** Accepting `society` in the payload and validating it.
- **Why:** If the client can name the tenant, every write is a potential cross-tenant write. A test posts a foreign `society` id and confirms it is ignored.

## 015 — Deny by default, per HTTP method (2026-10-20)
- **Chose:** `required_capabilities` is a dict from HTTP method to capability. Any method not listed is denied.
- **Rejected:** One capability per view.
- **Why:** Reads and writes need different privileges (a treasurer may read flats but not create them). Permissions run before method dispatch, so an unlisted method like DELETE returns 403 rather than 405, which is the safer behaviour.

## 016 — Missing permission prerequisites fail loudly (2026-10-20)
- **Chose:** `HasCapability` raises `ImproperlyConfigured` if `request.membership` is absent (wrong class order). `SocietyScopedView` fixes the order in one place.
- **Rejected:** Defaulting to allow or deny when the prerequisite is missing.
- **Why:** A silent default is how a permission bug becomes a data leak. A crash in development is caught immediately. A test swaps the order and expects the error.

## 017 — Session authentication with CSRF protection (2026-10-20)
- **Chose:** Django sessions via DRF `SessionAuthentication`, with login, logout, me and csrf endpoints.
- **Rejected:** Token or JWT auth for now; Supabase Auth (decision 002).
- **Why:** No new dependency, and it fits a React app served from the same site. A test proves a session write without a CSRF token gets 403.
- **Revisit:** If the frontend is hosted on a different domain (M5/M6), cross-site cookies get awkward and token auth becomes the alternative.

## 018 — Throttled, non-enumerating login (2026-10-20)
- **Chose:** Unknown user and wrong password return the same 400 message. Login is throttled to 10 attempts per minute per client.
- **Rejected:** Distinct error messages; no throttle.
- **Why:** Different messages let an attacker list valid usernames, and no throttle allows password guessing.
- **Watch out:** Behind a proxy (Render) set `NUM_PROXIES` or every user shares one bucket. The default per-process cache means the limit is per worker; Redis (M3) fixes that.

## 019 — Systematic cross-tenant test suite with a coverage guard (2026-10-20)
- **Chose:** One parametrized test attacks every route with every HTTP method as an admin of another society and asserts 404 and that the target's data is unchanged. A guard test fails if a route in `societies/urls.py` is not in the suite. A mutation check (removing `for_society` from one view) was run once and made three tests fail.
- **Rejected:** Hand-written per-endpoint cross-tenant tests only.
- **Why:** Hand-written lists silently miss new routes. The attacker is an admin so a 404 can only come from isolation, not from missing privileges. Checking that data is unchanged matters because a 404 alone could hide a write that happened first.

## 020 — Balance is derived from the ledger, not stored (2026-10-20)
- **Chose:** `outstanding = sum(charges) - sum(payments)`, computed by a database aggregate every time (`selectors.outstanding_for_flat`).
- **Rejected:** A cached `balance` column on Flat.
- **Why:** A cached column can drift from the ledger, and every writer must remember to update it. Deriving it removes that bug class. Add a cache only if it becomes slow.

## 021 — Ledger is append-only in Python AND in Postgres (2026-10-20)
- **Chose:** `save()`/`delete()` and queryset `update()`/`delete()` raise `AppendOnlyError`; a Postgres trigger (migration `0002`) raises on any `UPDATE` or `DELETE`.
- **Rejected:** Python guard only.
- **Why:** The ORM guard stops mistakes in app code; the trigger also stops raw SQL, scripts and future migrations. `TRUNCATE` does not fire row triggers, which is what lets the test runner flush tables.

## 022 — Corrections are reversing entries (2026-10-20)
- **Chose:** `reverse_entry` appends the opposite kind with `reverses` -> original (`OneToOne`, so reversed at most once). A reversal cannot itself be reversed. A charge cannot be reversed while the flat has paid it (reverse the payment first).
- **Rejected:** Signed amounts; editing in place; reversing a reversal.
- **Why:** Positive amounts plus `kind` keep the balance formula free of special cases, and history is never rewritten. Refusing to create credit keeps the "never overpaid" rule true for reversals too.

## 023 — Overpayment is rejected (2026-10-20)
- **Chose:** A payment larger than what the flat owes is refused (400).
- **Rejected:** Allowing credit/advance payments.
- **Why:** Simpler rule, and it makes the check-then-act race real so the row lock is genuinely needed and testable. Advance payments are out of scope.

## 024 — Row lock on the flat for every money write (2026-10-20)
- **Chose:** `record_payment` and `reverse_entry` start with `Flat.objects.for_society(society).select_for_update().get(...)`, then recompute the balance, then insert. Postgres runs at READ COMMITTED, so a waiting request sees the previous winner's commit.
- **Rejected:** `SERIALIZABLE` with retries; advisory locks; optimistic version counters; an in-process mutex (breaks with several workers).
- **Why:** The simplest mechanism with an obvious scope (one flat). Proven by parallel tests, and by removing the lock to watch them fail (10 of 10 payments succeeded).
- **Limit:** Works because all workers share one Postgres.

## 025 — Idempotency-Key header for payments (2026-10-20)
- **Chose:** Optional `Idempotency-Key` header (max 64 chars). Same key and same request returns the original entry (200, `created=False`); the same key with a different request is 409. Stored as a nullable column with a partial unique constraint per society. The key is checked before the overpayment rule so a retry after a full payment still succeeds.
- **Rejected:** Server-side deduplication by amount/time; empty-string keys.
- **Why:** Double clicks and network retries must not pay twice. NULL (not `''`) because a unique constraint ignores NULLs but would make `''` collide with itself.

## 026 — Object-level permission: residents see only their own flat, 404 otherwise (2026-10-20)
- **Chose:** `OwnFlatOrAllBalances.has_object_permission` raises `NotFound`. All lookups in the ledger views share one `get_or_404` so the response body is identical for missing, other-society and not-yours.
- **Rejected:** 403 for a neighbour's flat; DRF's `get_object_or_404` (its message differs from `NotFound()`).
- **Why:** A different body or status lets a resident learn which flats exist. A test compares the two responses byte for byte; it caught exactly this bug.

## 027 — Money is a string on the wire, always via a DecimalField (2026-10-20)
- **Chose:** Responses build money through serializers (`FlatLedgerSerializer`, `LedgerEntrySerializer`); tests assert on `response.json()`, not `response.data`.
- **Rejected:** Putting a raw `Decimal` into a response dict.
- **Why:** DRF's JSON encoder turns a bare `Decimal` into a float (`70.0`). Only a serializer `DecimalField` renders the exact string `"70.00"`.

## 028 — M2 scope cuts (2026-10-20)
- **Chose:** No HTTP endpoint for charges (the M3 billing job creates them through `record_charge`); ledger list capped at the newest 200 entries; AuditLog deferred to M4 with a marked spot inside `record_payment`.
- **Why:** Protects the timeline and keeps M2 on the guarantees (locking, idempotency, immutability).

## 029 — Billing is one transaction guarded by UNIQUE(society, period) (2026-10-20)
- **Chose:** `run_billing` inserts the `BillingRun` row and every charge in a single `transaction.atomic()`. `UNIQUE(society, period)` on `BillingRun` is the exactly-once guarantee. A second run finds the first and returns `created=False`; a racing worker blocks on the unique index, gets an `IntegrityError`, and returns the winner's run.
- **Rejected:** One transaction per flat with a status column (`pending`/`done`) to resume after a crash; a Redis lock; checking "already billed" in Python only.
- **Why:** One transaction makes a month fully billed or not billed at all, so there is no half-billed state to reason about and no resume logic. A Python-only check cannot stop two workers racing; the unique constraint can.
- **Proven by:** run-twice test, 10-thread test, simulated crash halfway (nothing left behind, rerun succeeds). Mutation: removing the `IntegrityError` handler fails the 10-thread test. Removing the early "already billed" exit changed nothing, because the constraint plus handler already cover it: the early exit is only an optimization.
- **Limit:** one transaction per society holds locks for the whole run. Fine for hundreds of flats; thousands would need batching.

## 030 — Second guard on the ledger: UNIQUE(flat, billing_run) (2026-10-20)
- **Chose:** Nullable `LedgerEntry.billing_run` with a partial unique constraint on `(flat, billing_run)`.
- **Rejected:** Relying on `BillingRun` alone.
- **Why:** Defense in depth. If the run-level check ever had a bug, the database still refuses a second charge for the same flat in the same run. It also links every automatic charge to the run that made it.

## 031 — Beat runs daily; idempotency makes that a feature (2026-10-20)
- **Chose:** `billing.bill_all_societies` at 01:00 Asia/Kolkata every day, always targeting the current month, fanning out one `billing.bill_society(society_id, period)` task per society.
- **Rejected:** Running only on the 1st.
- **Why:** The first run of the month does the work and later runs are no-ops, so a missed 1st (scheduler down, deploy) is caught up on the next tick without any special code.

## 032 — Celery tasks are idempotent, so acks_late is safe (2026-10-20)
- **Chose:** `CELERY_TASK_ACKS_LATE` and `CELERY_TASK_REJECT_ON_WORKER_LOST`: a task is acknowledged only after it finishes, so a worker that dies mid-task gets it redelivered.
- **Rejected:** The default early acknowledgement (a crash would silently lose the month's billing).
- **Why:** Redelivery means at-least-once execution, which is only correct because `run_billing` is idempotent. Task arguments are plain JSON (an int and an ISO date string); results are JSON-safe (money as strings).

## 033 — Per-flat monthly amount; schedule in settings; Redis only in dev (2026-10-20)
- **Chose:** `Flat.monthly_maintenance` (Decimal, default 0 = not billed, CHECK >= 0), editable by admins through the flat endpoint. The beat schedule lives in settings, with no `django-celery-beat`. Tests run tasks eagerly (`CELERY_TASK_ALWAYS_EAGER`); Redis runs in docker-compose for development.
- **Rejected:** One rate per society; `django-celery-beat` (an extra dependency and tables for a schedule that never changes at runtime).
- **Why:** Flats differ in size, and the extra field is one column. Eager mode keeps the test suite free of Redis.
- **Windows note:** run the worker with `--pool=solo`; Celery's prefork pool does not work on Windows.

## 034 — AuditLog is written inside the money transaction, and refuses to run outside one (2026-10-20)
- **Chose:** `audit.record()` is called inside `record_payment`, `reverse_entry`, `run_billing` and the expense services, and raises if no transaction is open. A failure writing the audit row rolls back the money change; a failed money change leaves no audit row.
- **Rejected:** Writing the audit row after the transaction (or from a signal/Celery task).
- **Why:** An after-the-fact write can crash between the two and leave money with no trail, or a trail for money that never moved. Proven by tests that make the audit write fail and check the payment and the whole billing month roll back.

## 035 — Audit rows only for real actions, never for replays or rejections (2026-10-20)
- **Chose:** An idempotent replay, an already-billed month and a rejected payment write no audit row.
- **Rejected:** Logging every attempt.
- **Why:** The log records what changed the books. Attempts that changed nothing would bury real actions.

## 036 — AuditLog stores its target as (object_type, object_id), not a foreign key (2026-10-20)
- **Chose:** Plain columns plus a small JSON `data` (money inside it as strings). The only foreign keys are society, actor and flat.
- **Rejected:** Generic foreign keys or one FK per audited table.
- **Why:** The audit app depends on nothing, a row can never block or cascade a deletion, and new audited actions need no migration.

## 037 — Append-only machinery shared in apps/core (2026-10-20)
- **Chose:** `AppendOnlyModel`, `AppendOnlyQuerySet` and an `append_only_trigger(table)` migration helper, used by LedgerEntry, Expense and AuditLog.
- **Rejected:** Copying the guard into each app.
- **Why:** One tested implementation of the two-layer guarantee (Python guard plus Postgres trigger). `validate_amount` moved to `core/money.py` for the same reason.

## 038 — Expenses are append-only with reversals, and use no row lock (2026-10-20)
- **Chose:** `Expense` with `reverses` (OneToOne: reversed at most once, a reversal cannot be reversed), counted as negative in `total_spent`. Idempotency by unique key: the loser of a race catches the `IntegrityError` and reads the winner's row.
- **Rejected:** Editing or deleting expenses; locking a parent row.
- **Why:** Unlike payments there is no balance to protect, so a lock buys nothing; the unique constraints decide every race. Mutation check: removing the loser's read-back fails the 10-thread test.
- **Limit:** Categories are validated by Django choices only (no DB CHECK); the list can change without a migration.

## 039 — Frontend: React + TypeScript + Vite + Mantine + TanStack Query, in `frontend/` (2026-10-20)
- **Chose:** React 19, Vite, TypeScript (strict), React Router, TanStack Query and Mantine, all versions pinned exactly. Cards everywhere (no data tables), a header on wide screens and a bottom navigation bar on phones. A warm "friendly community" theme with a dark-mode toggle.
- **Rejected:** shadcn/ui + Tailwind (more assembly for the same result in a limited UI budget); a charts library (collections vs outstanding is a plain progress bar); a form library (the three forms are small); a frontend test runner for now.
- **Why:** The UI is the smallest part of this project and should cost the least time. Mantine gives accessible, mobile-friendly components out of the box.
- **Not yet covered:** there are no automated frontend tests (only `tsc` and manual browser checks).

## 040 — In development, Vite proxies /api to Django (2026-10-20)
- **Chose:** The browser only talks to Vite; `/api` is forwarded to Django. Session cookie and CSRF are therefore same-origin, with no CORS dependency.
- **Rejected:** `django-cors-headers` with cross-origin cookies.
- **Why:** Simplest thing that works with decision 017 (session auth). The client fetches `/auth/csrf/`, sends `X-CSRFToken` on writes, forgets the token after login and logout (Django rotates it), and retries once on a stale-token 403.
- **Revisit at M5:** if the frontend is deployed on a different domain from the API, cookies become cross-site and either a shared parent domain or token auth is needed.

## 041 — Money is a string in the browser, never a JS number (2026-10-20)
- **Chose:** Amounts stay decimal strings end to end. `lib/money.ts` does formatting, validation and comparison with BigInt cents; Indian digit grouping; headline cards drop a redundant ".00" but non-zero paise are always shown. Every payment or expense form creates an `Idempotency-Key` when it opens.
- **Rejected:** `Number`/`parseFloat`, `NumberInput` components (they return floats).
- **Why:** Floats cannot represent most cents. The idempotency key makes a double tap or retry harmless, which is the M2 guarantee reaching the UI.

## 042 — UI role guards are convenience; the server is the authority (2026-10-20)
- **Chose:** The society id lives in the URL (`/s/:societyId/...`, mirroring the API). `RequireRole` redirects instead of showing broken pages, but every request is still checked server-side (decisions 009, 012).
- **Why:** A guard in the browser can be bypassed by anyone; it only exists for usability.

## 043 — Every API error is field-keyed, and the UI has one reader for all shapes (2026-10-20)
- **Incident:** Adding an existing member was refused by the server (400, no row added) but the response was a bare list, and the dialog only displayed errors keyed by field name, so the user saw nothing.
- **Chose:** Domain errors are raised keyed by field (`add_member` -> `user`/`flat`, mapped to the API's `username`); unique-constraint races are caught and mapped to the same message. In the frontend, `ApiError.fieldErrors()` accepts every DRF shape (object, string, bare list, `detail`) and `generalError()` shows anything not tied to an input, so no error can be dropped silently.
- **Why it slipped through:** the test only asserted `status_code == 400`. Tests for failures now assert the response **body**.

## 044 — Read-only `reports` app and a `seed_demo` command (2026-10-20)
- **Chose:** `summary/` (billed, collected, outstanding, spent, per flat) and `activity/` (newest payments) in a model-less `reports` app. All figures are net of reversals. `seed_demo` builds a demo society through the real services (billing, payments, a reversal, expenses), so the audit log is populated too, inside one transaction.
- **Rejected:** Seeding with raw inserts (would skip the invariants); a default demo password (the password is passed with `--password` or `DEMO_PASSWORD`).
- **Limit:** the ledger is append-only, so a seeded society cannot be wiped; use another `--slug`, or drop the local database.
