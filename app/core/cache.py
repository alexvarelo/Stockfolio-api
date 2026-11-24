"""Small TTL cache layer.

`CacheBackend` is the interface; `TTLCacheBackend` is the in-process
implementation (cachetools). A Redis-backed class implementing the same
three methods can replace it without touching callers.
"""
import threading
from typing import Any, Callable, Optional, Protocol

from cachetools import TTLCache

# TTLs in seconds
PRICE_TTL = 120            # prices: 1-5 min
DAILY_HISTORY_TTL = 12 * 3600   # daily history: 12 h
FINANCIALS_TTL = 24 * 3600      # financial statements: 24 h


class CacheBackend(Protocol):
    def get(self, key: str) -> Optional[Any]: ...
    def set(self, key: str, value: Any) -> None: ...
    def get_or_set(self, key: str, factory: Callable[[], Any]) -> Any: ...


class TTLCacheBackend:
    """Thread-safe in-memory TTL cache."""

    def __init__(self, ttl: float, maxsize: int = 1024):
        self._cache: TTLCache = TTLCache(maxsize=maxsize, ttl=ttl)
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            return self._cache.get(key)

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._cache[key] = value

    def get_or_set(self, key: str, factory: Callable[[], Any]) -> Any:
        """Return the cached value, or compute it with `factory` (not cached if it raises)."""
        cached = self.get(key)
        if cached is not None:
            return cached
        value = factory()
        if value is not None:
            self.set(key, value)
        return value


price_cache: CacheBackend = TTLCacheBackend(PRICE_TTL)
daily_history_cache: CacheBackend = TTLCacheBackend(DAILY_HISTORY_TTL, maxsize=512)
financials_cache: CacheBackend = TTLCacheBackend(FINANCIALS_TTL, maxsize=256)
