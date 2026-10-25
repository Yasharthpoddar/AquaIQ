"""Process-local concurrency, defensive copies and bounded cache behavior."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

import pytest

from models.forecast_cache import ForecastCache


def test_duplicate_concurrent_requests_compute_once_and_return_independent_values():
    cache = ForecastCache(2)
    start = Barrier(5)
    release = Event()
    entered = Event()
    calls = []
    def compute():
        calls.append(1)
        entered.set()
        assert release.wait(5)
        return {'status':'forecast', 'forecast':[3.]}
    def request():
        start.wait(5)
        return cache.get_or_compute('same-key', compute)
    with ThreadPoolExecutor(4) as pool:
        futures = [pool.submit(request) for _ in range(4)]
        start.wait(5)
        assert entered.wait(5)
        release.set()
        values = [f.result(timeout=5) for f in futures]
    assert len(calls) == 1
    values[0]['forecast'][0] = -1
    assert all(value['forecast'] == [3.] for value in values[1:])
    assert cache.get_or_compute('same-key', compute)['forecast'] == [3.]


def test_eviction_is_bounded_and_unavailability_is_not_a_success():
    cache = ForecastCache(2)
    calls = []
    def compute(key):
        calls.append(key)
        return {'status':'insufficient_data', 'forecast':[]}
    for key in ('a','b','a','c','b'):
        cache.get_or_compute(key, lambda: compute(key))
    assert calls == ['a','b','c','b']
    for _ in range(2):
        cache.get_or_compute('failure', lambda: calls.append('failure') or {'status':'model_unavailable'})
    assert calls.count('failure') == 2


def test_computation_error_does_not_poison_retries():
    cache = ForecastCache(2)
    def fail():
        raise RuntimeError('broken')
    with pytest.raises(RuntimeError, match='broken'):
        cache.get_or_compute('a', fail)
    assert cache.get_or_compute('a', lambda: {'status':'forecast'}) == {'status':'forecast'}
