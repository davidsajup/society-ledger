import time

import pytest

from apps.ledger import services


@pytest.fixture
def widen_race_window(monkeypatch):
    """Sleep right after the balance is read, before the insert.

    With the row lock this only makes requests queue up (slower, still correct). Without the
    lock it makes the check-then-act race nearly certain, so a missing lock cannot hide behind
    lucky timing.
    """
    real = services.outstanding_for_flat

    def slow(flat):
        owed = real(flat)
        time.sleep(0.05)
        return owed

    monkeypatch.setattr(services, "outstanding_for_flat", slow)
