import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("society_ledger")
# Reads every CELERY_* setting from Django settings (broker URL, schedule, ...).
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
