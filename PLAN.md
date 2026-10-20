# Plan

**Current task:** M0 — Bootstrap (in progress)

Budget: ~10 h/week on this project. Job applications start early February 2027 (~15 weekends from 2026-10-20).
Rule: backend milestones (M1–M5) are protected. If we slip, M6 (frontend) shrinks first.

| # | Weeks | Milestone | Done when this test/proof exists |
|---|---|---|---|
| M0 | 1 | Bootstrap: Docker, Django + DRF, Supabase connection, pytest, docs | Health check hits Supabase; `pytest` green on local db-test |
| M1 | 2–3 | Society, Flat, Membership (role), DRF auth, tenant-scoped querysets + permissions | Cross-tenant access test: user of society A gets 404 on society B's objects |
| M2 | 4–6 | Append-only LedgerEntry, Decimal money, `record_payment` service (`transaction.atomic` + `select_for_update`) | Parallel-payments test: N concurrent requests, no double credit |
| M3 | 7–8 | Redis + Celery beat monthly billing, idempotent via unique (society, period) BillingRun | Billing-run-twice test: second run creates zero charges |
| M4 | 9 | Expenses + AuditLog for every money action | Audit row is written in the same transaction (rollback test) |
| M5 | 10 | GitHub Actions CI (Postgres service) + deploy (Render + Supabase prod project) | Green CI badge, live URL |
| M6 | 11–14 | React + TS frontend: resident dashboard, treasurer dashboard, admin page | Usable demo on phone width |
| M7 | 15 | README, architecture diagram, decisions cleanup | Portfolio-ready repo |
| Later | — | Supabase Storage for receipts (+ AI extraction), optional RLS hardening, AI finance Q&A | — |

## M0 checklist
- [x] Project docs (CLAUDE.md, PLAN.md, domain rules, decisions)
- [x] Django + DRF skeleton, settings from env
- [x] Docker Compose: `web` + `db-test`
- [x] Health endpoint + test
- [ ] You: create Supabase project, put session-pooler URL in `.env`, run migrate, hit `/api/health/`
