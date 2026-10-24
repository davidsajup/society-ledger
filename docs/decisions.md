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

## 045 — Demo mode: passwordless one-click logins, off by default (2026-10-20)
- **Chose:** `DEMO_MODE` (default False) plus an explicit `DEMO_USERS` allowlist. `POST /auth/demo-login/` logs in an allowlisted username without a password, and only if that user is active and is neither staff nor superuser. `GET /auth/demo/` tells the login page whether to show the role cards. A banner inside the app says it is fake data and offers "Switch role". A system check (`accounts.W001`) prints a warning on every startup while it is on. The endpoint is throttled, and every refusal is the same 404.
- **Rejected:** Publishing a shared demo password on the login page or in the JavaScript bundle; an always-on endpoint; exempting staff accounts.
- **Why:** A new visitor (a recruiter) has no credentials, and "ask the developer" is a dead end. A server-side switch keeps production safe by default, and no secret is ever published.
- **Tested:** unlisted, staff, superuser, inactive and made-up users are all refused identically; matching is exact (no case, partial or wildcard matches); off means 404 and no session is created.
- **Limits:** Visitors can change demo data. A deployed demo needs its OWN database, reseeded regularly. The ledger is append-only, so a reset means recreating the database, not deleting rows. Never enable it on a database with real data.

## 046 — Statements and receipts are derived, printable pages (2026-10-20)
- **Chose:** The statement's running balance is computed BACKWARDS from the server's outstanding amount, so it stays exact even though the API returns only the newest 200 entries. Receipts are numbered `R-<ledger entry id>` and show who received the money and the balance after; a reversed payment's receipt is stamped VOID. Printing uses the browser (print CSS, "Save as PDF"). The ledger API now returns `recorded_by` (with `select_related`, so no extra query per row).
- **Rejected:** A PDF library; a separate receipt table; counting forwards from zero.
- **Why:** The ledger already holds everything a receipt needs. A second store would be a second truth.

## 047 — Dues by month are DERIVED by paying the oldest dues first (2026-10-20)
- **Chose:** `GET /dues/` allocates each flat's net collected money across its billed months, oldest first, and reports paid / partial / unpaid per month. Reversed charges reduce their ORIGINAL month; reversed payments reduce what was collected. Months older than the 12 shown are still allocated first and still counted in `outstanding`.
- **Rejected:** Storing which month a payment is for; letting the treasurer allocate by hand.
- **Why:** It is a view, so it cannot drift from the ledger. Tested invariant: for every flat and across five awkward scenarios, the unpaid amounts add up exactly to the ledger balance.
- **Limit:** It is a convention, not a fact: a resident who meant to pay only October still shows August cleared. Societies usually work this way, and the page says so.

## 048 — Activity timeline and billing history are read-only views of existing data (2026-10-20)
- **Chose:** The audit log is rendered as sentences grouped by day, with filters; `GET /billing-runs/` lists which months were billed. Admin and treasurer only. The page states that the log cannot be edited or deleted.
- **Rejected:** A separate "activity" table (the audit log already is one); letting residents see it.
- **Why:** It surfaces the strongest property of the system (nothing happens without a trace) without new write paths.

## 049 — Admin-issued logins use RANDOM one-time passwords, never anything derived (2026-10-20)
- **Chose:** The admin creates a login (name, role, flat). The server generates a readable username (`ravi.a-101@sunrise-heights`, unique across societies because it includes the society slug) and a random 12-character password (`xxxx-xxxx-xxxx`, no look-alike characters, about 59 bits). The password is shown to the admin once and stored only as a hash.
- **Rejected:** A password derived from the flat number (the original proposal).
- **Why:** Flat numbers are public knowledge inside a society. A derived password means anyone who knows the layout can sign in as any resident until they change it, and can lock the real owner out by changing it first. The username is an identifier, not a secret, so deriving it is fine.
- **Tested:** the password is not guessable from the name, flat or society; it appears in no audit row, list response or log; the response is `Cache-Control: no-store`.

## 050 — Temporary passwords must be replaced at first login, enforced on the server, and expire (2026-10-20)
- **Chose:** `must_change_password` and `temp_password_expires_at` on the user (default 7 days, `TEMP_PASSWORD_DAYS`). While the flag is set, the default permission `IsSettledUser` (also used by every society-scoped view) answers 403 `password_change_required` everywhere except `me`, `logout` and `change-password`. After expiry even the correct password is refused (400 `credentials_expired`), without revealing whether a username exists, and the admin can re-issue.
- **Rejected:** "Change it within a fixed period" with a long-lived temporary password (weeks of exposure); enforcing the change only in the browser.
- **Why:** A rule that only the UI enforces is a suggestion. Putting it in the shared permission class means no endpoint can forget it, and a test hits every kind of endpoint.
- **Also:** changing a password keeps the current session and ends all others; it is validated by Django's validators, throttled and CSRF-protected.

## 051 — Re-issuing credentials is deliberately limited (2026-10-20)
- **Chose:** An admin can re-issue only for someone in THEIR society who belongs to no other society, and never for staff, superusers or themselves. A new temporary password ends the person's existing sessions. The action is audited (username, never the password).
- **Rejected:** Letting any admin reset any member.
- **Why:** Accounts are global but societies are tenants. If society A's admin could reset a password for someone who also belongs to society B, that is a cross-tenant account takeover. Tested with a person in two societies, a superuser and a staff user.

## 052 — Credentials are handed over by the admin, not emailed (2026-10-20)
- **Chose:** The temporary password is shown once in a dialog (Copy button, "shown only once" warning, no click-away dismissal). Printable slips and a one-time CSV come with the CSV import (phase B).
- **Rejected:** Email delivery (needs an email provider and puts passwords in inboxes); showing it again later (it is stored hashed, so that is impossible by design).
- **Limit:** If the admin loses it, they issue a new one.

## 053 — A server enum the UI does not know must not blank the page (2026-10-20)
- **Incident:** Adding two audit event types (login created, credentials re-issued) made the Activity page crash with a blank screen the first time one appeared, because the page looked up an icon for each event type and found none.
- **Chose:** The TypeScript union now lists every action, so the compiler flags missing cases; the page falls back to a neutral row for any future unknown action; and an `ErrorBoundary` around the page area shows "This page hit a problem" with a Reload button instead of a blank screen.
- **Why it slipped through:** the page was only checked against the events that existed when it was built, and the frontend has no automated tests.
- **Follow-up idea:** a backend test that every `AuditLog.Action` value appears in `frontend/src/api/types.ts`.

## 054 — Roles are president, secretary, treasurer, resident; `admin` is gone (2026-10-20)
- **Chose:** The old `admin` became `secretary` through a reversible data migration (`societies/0004`: drop the CHECK, convert rows, re-add the CHECK). President and secretary hold the same powers today; the capability table in `roles.py` is where they can diverge. Only the treasurer records expenses.
- **Rejected:** Keeping `admin` next to the new roles (nobody in a real society holds that title); a president who can only read (the society wanted a backup person to collect payments).
- **Why:** The roles should match how the society actually works. Moving rows inside a migration, with the constraint dropped first, keeps the database valid at every step.

## 055 — Office-bearers can have a flat (2026-10-20)
- **Chose:** A flat is required for a resident and optional for every other role. The existing CHECK (`resident_requires_flat`) already allowed this, so no schema change was needed beyond the role list.
- **Rejected:** Giving an office-bearer two memberships (one per hat): it doubles the rows and lets the same person hold two roles.
- **Why:** The president, secretary and treasurer are also residents who pay dues. One role per person, plus a flat, models that without special cases.

## 056 — Nobody records or reverses a payment for their own flat (2026-10-20)
- **Chose:** `refuse_own_flat` in the ledger service rejects any actor who has a membership on the target flat (so housemates are covered too). It runs before the row lock, returns 403 and writes nothing. The UI hides the buttons, but the server is the real control.
- **Rejected:** A UI-only rule; comparing only the actor's own flat id (misses a second login in the same flat).
- **Why:** This is segregation of duties. A treasurer who could mark their own dues paid is the exact fraud an accounting system exists to prevent. Interview framing: "the person with write access to the ledger must not be able to clear their own debt."
- **Tested:** `test_self_dealing.py`, including mutation checks (remove the guard, tests fail).

## 057 — Changing a role has guard rails (2026-10-20)
- **Chose:** `PATCH members/<id>/`. Not on yourself; resident needs a flat; the flat must be in this society; the society must keep at least one manager. The managers are locked `ORDER BY pk` before the check, and the target is re-read with `FOR UPDATE OF self`. Audited as `member.updated` with before and after values.
- **Rejected:** Allowing self-demotion (a lone manager could lock the society out); checking the manager count without locks (two managers demoting each other at once would both pass); an unordered lock (two requests could deadlock).
- **Why:** This is a check-then-act race, the same family as double-crediting. The lock turns the check into a guarantee.

## 058 — Where office-bearers see their own dues (2026-10-20)
- **Chose:** A "Your dues" card on Overview and "My flat" in the account menu. Flats and Residents merged into one People tab so the phone bottom bar stays at five items. Routes are guarded by capability or "has a flat", not by role name.
- **Rejected:** A role switcher; a sixth bottom-bar item.
- **Why:** Seeing your own dues is a resident capability, not a resident role. Deciding by capability stops the UI from assuming "only residents have flats".

## 059 — The super admin is a platform flag, not a society role (2026-10-24)
- **Chose:** A Django superuser (`is_superuser`) who belongs to **no** society. `IsPlatformAdmin` (apps/onboarding/permissions.py) guards `/api/platform/`, which can create a society and its first president's login, list societies (counts and logins only) and reissue a lost president/secretary password. Every `/api/societies/<id>/` route still answers 404 to them.
- **Rejected:** A `Membership` role called "super admin" (it would live inside one tenant); a super admin who can read every society's books (one stolen password would expose all of them); using the Django admin site (it bypasses the services, so no audit rows and no password rules).
- **Why:** Someone has to be above the societies to create them, but that power must not become a tenant escape hatch. The blast radius of a compromised super admin is "can create societies", not "can read everyone's money".
- **Tested:** `apps/onboarding/tests/test_platform_api.py` (every society role refused; atomic creation; the password in one response only) and `test_cross_tenant.py` (the super admin gets 404 on every society route with every method). Mutation checks on the permission, the service guard and the `me` flag all fail the suite.

## 060 — Billing cycle belongs to the society, and automatic billing waits for a start date (2026-10-24)
- **Chose:** `Society.billing_cycle_months` (1 or 3) and `Society.billing_start`. `current_period(today, cycle)` returns the first day of the cycle (1 Jan/Apr/Jul/Oct for quarterly). `run_billing` refuses a period that is not a cycle start. The daily job computes the period per society and skips a society until its `billing_start`. `Flat.monthly_maintenance` was renamed `maintenance_amount` (a true `RenameField`, reversible, tested on real rows) because it now means "per cycle".
- **Rejected:** Keeping the old field name for quarterly amounts (a name that lies); splitting a quarterly fee into three monthly charges (does not divide evenly); a new `BillingRun` cycle field (the period date already identifies the cycle).
- **Why the start date:** the daily job bills "the current cycle" for every society. On 24 Oct that is the whole of Q4. Without a start date, giving a new quarterly society flats with amounts would charge it a full quarter it never agreed to. The start date makes setup safe.
- **Why it is still idempotent:** every day in a quarter maps to the same `(society, period)`, so the unique constraint makes every later run a no-op.

## 061 — Flexible payments are installments, not advance credit (2026-10-24)
- **Chose:** A quarterly charge can be paid in any number of partial payments (already how `record_payment` works), but a payment can never exceed what is owed.
- **Rejected:** Allowing payment in advance or a credit balance.
- **Why:** The "never overpaid" rule is what the row lock and the concurrency tests protect. Credit would need a new ledger concept and would change the dues grid's allocation. Installments give the flexibility residents asked for without touching the invariant.

## 062 — Phone and email live on Membership, not on User (2026-10-24)
- **Chose:** `Membership.phone` and `Membership.email`, set by the bulk import and shown only in the president/secretary member list.
- **Rejected:** `User.email` and a new `User.phone`.
- **Why:** A user is global; a person can belong to two societies. Contact details typed by society A's president must not follow that person into society B. The audit log stores counts and usernames only, and the super admin's list has no contact fields.

## 063 — Bulk import is preview, then confirm, and the server checks twice (2026-10-24)
- **Chose:** `imports/preview/` reads the file and returns rows and problems, writing nothing. `imports/confirm/` receives the rows as JSON (not the file), locks the society row with `select_for_update`, **re-validates every row inside the lock**, and creates flats, people and logins in one transaction.
- **Rejected:** Trusting the preview (the request body is whatever the client sends); validating once before the lock (a second import or a hand-added flat could land in between); creating rows as they parse; updating existing flats from the file (too easy to overwrite by accident, so an existing label is an error).
- **Why:** This is the same check-then-act family as double-crediting. Tests: an edited preview, a flat created between preview and confirm, confirming twice, and two simultaneous imports (one is created, one is cleanly refused). Removing the lock fails the race test; skipping re-validation fails five.

## 064 — Uploaded spreadsheets are untrusted input (2026-10-24)
- **Chose:** `.csv` and `.xlsx` only, 1 MB, 300 rows. Excel is opened read-only with `data_only=True` (formulas are never evaluated), first sheet only, and refused if it has macros or would unzip to more than 10 MB. `openpyxl` uses `defusedxml`, so an XML entity declaration is rejected. Nothing is stored.
- **Rejected:** `.xls`/`.xlsm`; evaluating formulas; storing the file for later.
- **Dependency (approved):** `openpyxl` and `defusedxml`.
- **Note:** my first entity test passed for the wrong reason (this openpyxl writes strings inline, so the file I tampered with did not exist). It now injects the entity into the sheet XML and has a harmless-comment control that must still parse.

## 065 — Login slips show the password once, and the CSV defends against formulas (2026-10-24)
- **Chose:** The confirm response is the only place passwords exist (`Cache-Control: no-store`). The browser shows printable slips and a CSV download, keeps them across tab switches, and asks "Leave without the passwords?" before discarding. Every CSV cell starting with `= + - @` gets a leading apostrophe.
- **Rejected:** Emailing passwords; storing them to show later; a CSV with raw cells.
- **Why:** A resident's name is typed by someone else. Opened in Excel, a name like `=HYPERLINK(...)` can run. Defusing every cell removes the risk.

## 066 — No opening balances: start at zero on a new quarter (2026-10-24)
- **Chose:** Everyone begins at zero at the start of a quarter; anything owed from before stays in the old Excel.
- **Rejected:** An opening-balance charge per flat; re-creating old months and payments (every row would be stamped with today's date, and one typo is permanent in an append-only ledger).
- **Why:** The simplest honest starting point. If a society ever needs arrears carried in, add one "opening balance" charge per flat through `record_charge`, as a separate decision.

## 067 — The idempotency key covers one attempt, and the browser's balance check is only a convenience (2026-10-24)
- **Chose:** The browser makes the key (`crypto.randomUUID()`) each time the payment form opens and sends it as `Idempotency-Key`. The server stores it on the ledger row, so only a payment that was written "uses" a key. Same key and same request returns the original entry (200); same key and a different request is a 409. A rejected request (overpayment) stores nothing, so retrying with the same key behaves like a first attempt. The browser also compares the typed amount with the balance it loaded, for instant feedback only.
- **Rejected:** A server-generated key (it would not exist yet when the first reply is lost); keeping the key in browser storage across reloads; trusting the browser's balance check.
- **Why:** The key is there to make a double tap or an automatic network retry safe, and the unique constraint per society backs it up if two retries race. The real overpayment check stays in the service, under the flat row lock, against the current balance.
- **Known gap:** If the reply is lost and the treasurer closes and reopens the form, the new key makes it look like a new payment. The balance check refuses it only when the flat owes no more than the amount; a quarter paid in installments can get a duplicate. It is visible on the dues grid and fixed with a reversal. Closing the gap means holding the key until the server confirms the outcome, or looking up the last payment on reopen; not worth it yet. **Closed by 068** with a server-side warning instead.

## 068 — A possible duplicate payment needs a deliberate yes (2026-10-24)
- **Chose:** `record_payment` looks for a live payment (not reversed, not a reversal entry) of the same amount on the same flat in the last 10 minutes, by anyone. If there is one and `confirm_duplicate` is not true, nothing is written and the API answers 409 `possible_duplicate` with the earlier payment's amount and time. The payment form shows "Is this the same payment?" and resends with `confirm_duplicate: true` only on "Yes, record it again". The confirmed override is stored in the audit row as `confirmed_duplicate_of`. Other 409s now carry a `code` so the browser can tell them apart.
- **Order of checks:** idempotent replay first (a retry is never warned), then overpayment (a hard error beats a soft warning), then the duplicate warning, all after the flat lock.
- **Rejected:** a hard ban on equal payments (two equal installments are normal, and a ban would block them); a browser-only check (a reload erases it, and the browser can be bypassed); looking only at the same person's payments (two office-bearers entering one cash receipt is as likely); looking up before the flat lock (two tabs submitting together would both pass).
- **Why:** the idempotency key stops a retry of one request, not a person who starts over. The balance check stops it only when the repeat would overshoot. This rule closes the middle case, a quarter paid in installments, by making the repeat deliberate.
- **Cost:** a genuine second equal installment inside 10 minutes needs one extra tap, and four existing tests that record equal amounts back to back now pass `confirm_duplicate=True` (the parallel-payments test, two query-count loops, the quarterly installments test), as does the demo seeder.
- **Tests:** 19, including one for the simultaneous case. Moving the lookup above the lock fails it; deleting the reversed, reversal, flat, window and confirm guards each fail a matching test.
