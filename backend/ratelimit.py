"""
OrbitGuard - small in-memory sliding-window rate limiter
---------------------------------------------------------
Used on login and registration to slow down password guessing and account spam.

Limits are kept in this process's memory, so they are per worker and reset on
restart. That is fine for the single-worker deployment this project targets; with
several workers/instances, move the counters to a shared store such as Redis.
"""

import threading
import time
from collections import deque


class SlidingWindowLimiter:
    """Allow at most `max_events` events per key within the last `window_seconds`."""

    def __init__(self, max_events: int, window_seconds: float, max_keys: int = 10_000):
        self.max_events = max_events
        self.window_seconds = window_seconds
        self.max_keys = max_keys
        self._events: dict[str, deque] = {}
        self._lock = threading.Lock()

    def _live(self, key: str, now: float) -> deque | None:
        dq = self._events.get(key)
        if dq is None:
            return None
        while dq and now - dq[0] >= self.window_seconds:
            dq.popleft()
        if not dq:
            del self._events[key]
            return None
        return dq

    def _retry_after(self, dq: deque | None, now: float) -> float:
        if dq is None or len(dq) < self.max_events:
            return 0.0
        return max(0.0, self.window_seconds - (now - dq[0]))

    def blocked_for(self, key: str) -> float:
        """Seconds until `key` may act again (0 if it may act now). Records nothing."""
        with self._lock:
            now = time.monotonic()
            return self._retry_after(self._live(key, now), now)

    def record(self, key: str) -> None:
        """Count one event for `key`."""
        with self._lock:
            now = time.monotonic()
            dq = self._live(key, now)
            if dq is None:
                self._evict_if_full(now)
                dq = self._events.setdefault(key, deque())
            dq.append(now)

    def hit(self, key: str) -> float:
        """Count an event if allowed. Returns 0 when allowed, else the seconds to wait (nothing recorded)."""
        with self._lock:
            now = time.monotonic()
            dq = self._live(key, now)
            retry = self._retry_after(dq, now)
            if retry:
                return retry
            if dq is None:
                self._evict_if_full(now)
                dq = self._events.setdefault(key, deque())
            dq.append(now)
            return 0.0

    def clear(self, key: str) -> None:
        with self._lock:
            self._events.pop(key, None)

    def reset(self) -> None:
        with self._lock:
            self._events.clear()

    def _evict_if_full(self, now: float) -> None:
        """Bound memory: drop expired keys, then the oldest keys, once max_keys is reached."""
        if len(self._events) < self.max_keys:
            return
        for k in list(self._events):
            self._live(k, now)
        while len(self._events) >= self.max_keys:
            self._events.pop(next(iter(self._events)))
