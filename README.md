# Society Ledger

A multi-tenant finance platform for housing societies, with flats, residents, monthly billing, a payments ledger, expenses and an audit log. Each society's data is isolated.

Stack: Django + DRF, PostgreSQL (Supabase), Redis + Celery (coming in M3), Docker Compose, pytest.

Status: see [PLAN.md](PLAN.md). Rules: see [docs/domain-rules.md](docs/domain-rules.md). Why things are the way they are: see [docs/decisions.md](docs/decisions.md).

## Setup

1. Create a Supabase project and get the connection string. In the dashboard, click **Connect**, then copy the **Session pooler** URI (host `*.pooler.supabase.com`, port **5432**).
2. Copy the env template and fill it in:
   ```bash
   cp .env.example .env
   ```
   - Set `DATABASE_URL` to the session-pooler URI with your database password, and add `?sslmode=require` to the end.
   - Set `DJANGO_SECRET_KEY` to a long random string. You can generate one with `python -c "import secrets; print(secrets.token_urlsafe(50))"`.
3. Build, migrate and run:
   ```bash
   docker compose run --rm web python manage.py migrate
   docker compose up --build web
   ```
4. Open http://localhost:8000/api/health/. It should return `{"status": "ok", "db": "ok"}`.

## Tests

Tests run against a local Postgres container (`db-test`), never against Supabase.

```bash
docker compose run --rm web pytest
docker compose run --rm web ruff check .
```
