import threading
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection

from apps.ledger.services import record_charge
from apps.societies.models import Flat, Society


def build_world(owed="100.00"):
    """A society, one flat that owes `owed` (None for no charge), and a treasurer user."""
    society = Society.objects.create(name="Green Park", slug="green-park")
    flat = Flat.objects.create(society=society, label="A-101")
    treasurer = get_user_model().objects.create_user(username="treasurer", password="x")
    if owed:
        record_charge(society=society, flat=flat, amount=Decimal(owed))
    return society, flat, treasurer


def run_in_parallel(n, fn):
    """Run fn(i) in n threads that all start at the same instant, each on its own connection."""
    barrier = threading.Barrier(n)

    def worker(i):
        try:
            connection.ensure_connection()  # connect BEFORE the barrier so all threads collide
            barrier.wait(timeout=10)
            return fn(i)
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=n) as pool:
        return list(pool.map(worker, range(n)))
