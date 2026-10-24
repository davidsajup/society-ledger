from pathlib import Path

import environ
from celery.schedules import crontab

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    DJANGO_ALLOWED_HOSTS=(list, []),
)
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env("DJANGO_DEBUG")
ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "apps.core",
    "apps.accounts",
    "apps.societies",
    "apps.ledger",
    "apps.billing",
    "apps.audit",
    "apps.expenses",
    "apps.reports",
    "apps.onboarding",
    "apps.imports",
]

AUTH_USER_MODEL = "accounts.User"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Supabase session pooler. See docs/decisions.md #003.
DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["CONN_MAX_AGE"] = 60
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    # Deny by default: every endpoint must opt in to public access explicitly.
    "DEFAULT_PERMISSION_CLASSES": ["apps.accounts.permissions.IsSettledUser"],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    # Throttle scopes used with ScopedRateThrottle. Behind a proxy (Render) the client IP comes
    # from X-Forwarded-For: set NUM_PROXIES at deploy time or all users share one bucket.
    "DEFAULT_THROTTLE_RATES": {
        "login": "10/min",
        "demo": "30/min",
        "password": "10/min",
        "import": "60/hour",
    },
    # Serialize Decimal as strings so money never passes through a float in JSON clients.
    "COERCE_DECIMAL_TO_STRING": True,
}

# --- Celery (broker: Redis) ---------------------------------------------------------------
CELERY_BROKER_URL = env("REDIS_URL", default="redis://localhost:6379/0")
CELERY_TIMEZONE = TIME_ZONE
# Acknowledge a task only AFTER it finishes, so a worker that dies mid-task gets it redelivered.
# That is only safe because every task here is idempotent (see apps/billing/services.py).
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_BEAT_SCHEDULE = {
    "bill-all-societies-daily": {
        "task": "billing.bill_all_societies",
        "schedule": crontab(hour=1, minute=0),  # 01:00 Asia/Kolkata, every day
    },
}

# --- Demo mode (passwordless logins for fake demo accounts; see apps/accounts/demo.py) ---
# OFF by default. Turn on only for a database that holds fake data.
DEMO_MODE = env.bool("DEMO_MODE", default=False)
DEMO_USERS = env.list("DEMO_USERS", default=[])

# Admin-issued logins: how long a temporary password stays valid if never used.
TEMP_PASSWORD_DAYS = env.int("TEMP_PASSWORD_DAYS", default=7)
