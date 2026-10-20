import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def clear_cache():
    """Throttle counters live in the cache; without this, tests would throttle each other."""
    cache.clear()
