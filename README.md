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
3. Create the virtual environment and install dependencies (Python 3.11+):
   ```bash
   python -m venv .venv
   .venv/Scripts/activate        # Windows; on macOS/Linux: source .venv/bin/activate
   pip install -r requirements-dev.txt
   ```
4. Migrate and run (this talks to Supabase):
   ```bash
   python manage.py migrate
   python manage.py runserver
   ```
5. Open http://localhost:8000/api/health/. It should return `{"status": "ok", "db": "ok"}`.

## Tests

Tests run against a local Postgres container (`db-test`, published on localhost:5433), never against Supabase.

```bash
docker compose up -d db-test
python -m pytest
python -m ruff check .
```

Docker also builds the production image (`docker compose build web`), but day-to-day development uses the venv.

## Frontend (React)

The UI lives in `frontend/` (React + TypeScript + Vite + Mantine). In development Vite proxies `/api` to Django, so both must be running.

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. Other commands: `npm run typecheck` and `npm run build`.

## Demo data

Create a demo society (12 flats, an admin, a treasurer, six residents, three billed months, payments and expenses). Pick your own password; it is not stored anywhere:

```bash
python manage.py seed_demo --password "choose-a-password"
```

Log in as `asha` (admin), `tara` (treasurer) or `ravi`, `meera`, `kiran`, `priya`, `john`, `nisha` (residents). The command does nothing if the society already exists. Billing can be run by hand with `python manage.py run_billing --period 2026-11`; running it twice bills once.
