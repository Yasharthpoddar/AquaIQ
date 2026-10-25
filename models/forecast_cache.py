"""Bounded process-local memoization with one computation per concurrent key."""
from collections import OrderedDict
from concurrent.futures import Future
from copy import deepcopy
from threading import RLock


class ForecastCache:
    def __init__(self, limit):
        self.limit = limit
        self._values = OrderedDict()
        self._pending = {}
        self._lock = RLock()

    def clear(self):
        """Evict completed values; in-flight work still completes under its original identity."""
        with self._lock:
            self._values.clear()

    def get(self, key):
        with self._lock:
            if key in self._values:
                self._values.move_to_end(key)
                return deepcopy(self._values[key])
            return None

    def set(self, key, value):
        with self._lock:
            self._values[key] = deepcopy(value)
            self._values.move_to_end(key)
            while len(self._values) > self.limit:
                self._values.popitem(last=False)

    def get_or_compute(self, key, compute):
        with self._lock:
            if key in self._values:
                self._values.move_to_end(key)
                return deepcopy(self._values[key])
            future = self._pending.get(key)
            owner = future is None
            if owner:
                future = self._pending[key] = Future()
        if not owner:
            return deepcopy(future.result())
        try:
            value = deepcopy(compute())
            with self._lock:
                # Deterministic lack of coverage is reusable; transient failures are not.
                if isinstance(value, dict) and value.get('status') in ('forecast', 'insufficient_data'):
                    self._values[key] = value
                    self._values.move_to_end(key)
                    while len(self._values) > self.limit:
                        self._values.popitem(last=False)
                future.set_result(value)
            return deepcopy(value)
        except BaseException as error:
            future.set_exception(error)
            raise
        finally:
            with self._lock:
                self._pending.pop(key, None)
