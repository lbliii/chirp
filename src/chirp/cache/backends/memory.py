"""In-process memory cache backend with TTL support.

Default backend — zero dependencies, dict-based.
Free-threading safe via threading.Lock on all mutations.
"""

import threading
import time


class MemoryCacheBackend:
    """In-process dict + TTL cache backend.

    Suitable for single-process development and small apps.
    Not shared between workers in multi-process production.
    Thread-safe for free-threaded Python (3.14t).
    """

    __slots__ = ("_lock", "_store")

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._store: dict[str, tuple[bytes, float]] = {}

    async def get(self, key: str) -> bytes | None:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            value, expires = entry
            if expires > 0 and time.monotonic() > expires:
                del self._store[key]
                return None
            return value

    async def set(self, key: str, value: bytes, ttl: int = 0) -> None:
        expires = time.monotonic() + ttl if ttl > 0 else 0.0
        with self._lock:
            self._store[key] = (value, expires)

    async def delete(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    async def clear(self) -> None:
        with self._lock:
            self._store.clear()
