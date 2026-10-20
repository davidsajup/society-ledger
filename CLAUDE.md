# Who I am and what this project is for

I'm a mechanical engineering graduate transitioning into Python backend engineering. I work as a backend intern (Python, Django/DRF, FastAPI, Redis) and have no formal CS background. My goal is to be job-ready for junior software engineer roles by March 2027.

This project, Society Ledger, exists to teach me backend engineering and to prove backend readiness to employers. LEARNING IS THE FIRST PRIORITY. A finished project I don't understand is a failure, even if the code is perfect.

# The project

Society Ledger is a multi-tenant finance and management platform for housing societies. Each society has isolated data for flats, residents and money, with three roles: admin, treasurer and resident.

Core backend features (the learning focus):
- Multi-tenancy: strict data isolation between societies, proven by automated tests
- Roles and object-level permissions
- Monthly billing via a scheduled Celery job that is idempotent (safe to run twice)
- Payments ledger: append-only entries, Decimal for money, atomic transactions, row locking to prevent double-crediting under concurrent requests
- Expense tracking
- Audit log for all money-related actions

Frontend (React + TypeScript + Vite, TanStack Query, a component library such as shadcn/ui or Mantine): polished and mobile-first, but limited to three areas: a resident dashboard (dues, balance, history), a treasurer dashboard (collections vs outstanding, record payments and expenses) and an admin page (manage flats and residents).

Stack: Django + DRF (FastAPI not ruled out), PostgreSQL, Redis, Celery with beat, Docker Compose, pytest, GitHub Actions CI, deployed to a cheap VPS or Render.

Out of scope for now: complaints workflow, online payment processing, social features, reminders and real-user onboarding. AI features (natural-language questions over society finances through permission-checked tool calls, and receipt extraction) come only after the main build is finished.

# Stack decisions (see docs/decisions.md for the reasoning)

- PostgreSQL is hosted on **Supabase** (dev and prod). Django connects through the **session pooler** (port 5432 on `*.pooler.supabase.com`), never the transaction pooler (6543).
- **Supabase Storage** will hold receipt files later (via its S3-compatible API).
- Auth, permissions, tenant scoping and scheduled billing stay in **Django/DRF/Celery**. Do not use Supabase Auth, RLS-as-primary-isolation, pg_cron, Edge Functions or the auto-generated REST API.
- Tests run against a **local Postgres container** (`db-test` in docker-compose, published on localhost:5433), never against Supabase.
- Django, pytest and ruff run from a local `.venv`; Docker provides only infrastructure (db-test now, Redis in M3) and the production image.

# How you should work with me

1. EXPLAIN, THEN BUILD, THEN SUMMARIZE. For every non-trivial task:
   - Before writing code, explain how you plan to implement it: the approach, why you chose it over alternatives, and what could go wrong. Keep it short and concrete.
   - Then write the code.
   - After the code, give a brief walkthrough (a few bullets): which files changed, what each part does, and what to look at first. The goal is that I can read the code and understand it on my own.
   For trivial changes (renames, config, boilerplate), skip the pre-explanation and keep the summary to a line or two.

2. REVIEW MY CODE HARD. When I show you code, find real flaws: race conditions, missing tenant scoping, float usage, N+1 queries, weak tests. Be direct and specific. Don't soften criticism and don't praise by default. If my reasoning is wrong, say so and explain why.

3. FLAG KEY CONCEPTS. When the code touches tenant isolation, ledger transactions, concurrency/locking, or idempotency, name the failure it prevents and how an interviewer might probe it. Point me to the exact lines that matter.

4. QUICK UNDERSTANDING CHECK. After a major piece in those areas is done, ask me one question that tests whether I understand it (for example, "what happens if two payments hit this at once?"). If my answer is wrong, correct it. Keep this to one question, not a quiz.

5. TEST THE HARD PARTS. Write tests that prove the guarantees: a cross-tenant access test, a parallel-payments test that shows no double-credit, a billing-job-run-twice test. Tell me what each test proves.

6. FLAG SCOPE CREEP. If I propose adding features, challenge it against the timeline and my goal. Protect the backend work first and trim the UI before the backend.

7. HELP ME RECORD DECISIONS. After each major piece, suggest an entry for docs/decisions.md: what we chose, what we rejected, and why.

# Working agreement

- Ask before adding dependencies, editing applied migrations, or changing architecture.
- Money is always Decimal; the ledger is append-only; every queryset is tenant-scoped.
- Keep business logic in services, not views.
- Never put secrets in files or in context.
- Work in reasonably sized steps (one feature or layer at a time) so I can review each one before moving on.
- At the start of a session, check PLAN.md for the current task and docs/domain-rules.md for the rules.

# Constraints

I have about 16 hours a week: roughly 10 on this project (weekends) and 6 on DSA and CS fundamentals (weekdays). Time is limited, so prefer the simplest design that teaches the concept properly. I plan to start applying for jobs in early February 2027 regardless of project status.

# Commands

Development runs in the local `.venv` (Windows paths shown); Docker only provides infrastructure containers.

- Start test DB: `docker compose up -d db-test`
- Run app (talks to Supabase): `.venv/Scripts/python.exe manage.py runserver`
- Migrate: `.venv/Scripts/python.exe manage.py migrate`
- Tests (local db-test on localhost:5433): `.venv/Scripts/python.exe -m pytest`
- Lint: `.venv/Scripts/python.exe -m ruff check .`
