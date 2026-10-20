"""Test settings: same as dev, but the database is the local db-test container, never Supabase."""

import os

# settings.py requires these; tests must not depend on a real .env.
os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-not-secret")
os.environ.setdefault("DATABASE_URL", "postgres://unused:unused@localhost:5432/unused")

from .settings import *  # noqa: E402, F403
from .settings import env  # noqa: E402

DATABASES = {
    "default": env.db(
        "TEST_DATABASE_URL",
        default="postgres://ledger:ledger@localhost:5433/ledger_test",
    )
}

# Fast hashing keeps user-creating tests quick.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Run Celery tasks inline so tests need no Redis, and surface task errors in the test.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# A developer's .env may enable demo mode; tests must always start with it off.
DEMO_MODE = False
DEMO_USERS = []
