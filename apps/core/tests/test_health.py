import pytest
from django.db import connection
from django.urls import reverse
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_health_returns_ok_and_hits_database():
    response = APIClient().get(reverse("health"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "ok"}


@pytest.mark.django_db
def test_tests_run_on_postgres_not_sqlite():
    # select_for_update is a no-op on SQLite, so the concurrency tests in M2 are only
    # meaningful on Postgres. Fail loudly if settings ever drift.
    assert connection.vendor == "postgresql"
