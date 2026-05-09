"""Deferred-value cache for Suspense context values.

``DeferredCache`` stores successful async factory results behind explicit app
or route-owned cache instances.  On a warm hit it returns the cached value
directly; on a miss it returns an awaitable that resolves and stores the value.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, cast

from anyio.to_thread import run_sync


@dataclass(frozen=True, slots=True)
class _CachedValue:
    value: object
    expires_at: float


class _SharedDeferred[T]:
    """Awaitable shared by all consumers for one in-flight cache key."""

    __slots__ = (
        "_cache",
        "_condition",
        "_done",
        "_exception",
        "_factory",
        "_key",
        "_result",
        "_started",
        "_ttl",
    )

    def __init__(
        self,
        cache: DeferredCache,
        key: str,
        factory: Callable[[], Awaitable[T]],
        ttl: float,
    ) -> None:
        self._cache = cache
        self._key = key
        self._factory = factory
        self._ttl = ttl
        self._condition = threading.Condition()
        self._started = False
        self._done = False
        self._result: T | None = None
        self._exception: BaseException | None = None

    def __await__(self) -> Any:
        return self._await().__await__()

    def close(self) -> None:
        """Discard an unstarted deferred value.

        Suspense calls ``close()`` on awaitables when validation fails before
        scheduling them. Removing the in-flight entry keeps a rejected render
        from pinning the key forever.
        """
        with self._condition:
            if self._started or self._done:
                return
            self._exception = RuntimeError("DeferredCache awaitable was closed before it ran.")
            self._done = True
            self._condition.notify_all()
        self._cache._discard_inflight(self._key, self)

    async def _await(self) -> T:
        if self._claim_leader():
            try:
                result = await self._factory()
            except BaseException as exc:
                self._finish_exception(exc)
                raise
            else:
                self._cache._store_success(self._key, result, self._ttl, self)
                self._finish_success(result)
                return result

        return await run_sync(self._wait_result)

    def _claim_leader(self) -> bool:
        with self._condition:
            if self._done:
                return False
            if self._started:
                return False
            self._started = True
            return True

    def _finish_success(self, result: T) -> None:
        with self._condition:
            self._result = result
            self._done = True
            self._condition.notify_all()

    def _finish_exception(self, exc: BaseException) -> None:
        self._cache._discard_inflight(self._key, self)
        with self._condition:
            self._exception = exc
            self._done = True
            self._condition.notify_all()

    def _wait_result(self) -> T:
        with self._condition:
            while not self._done:
                self._condition.wait()
            if self._exception is not None:
                raise self._exception
            return cast(T, self._result)


async def _resolve_uncached[T](factory: Callable[[], Awaitable[T]]) -> T:
    return await factory()


class DeferredCache:
    """Small explicit TTL cache for Suspense deferred values.

    Use one cache instance per app, service, or route module. The cache stores
    successful factory results only. Warm hits return the value synchronously,
    so ``Suspense`` renders that value in the initial shell. Misses return an
    awaitable, preserving the existing shell-plus-deferred-OOB Suspense path.
    """

    __slots__ = ("_data", "_default_ttl", "_inflight", "_lock")

    def __init__(self, *, default_ttl: float = 300.0) -> None:
        self._default_ttl = float(default_ttl)
        self._data: dict[str, _CachedValue] = {}
        self._inflight: dict[str, _SharedDeferred[Any]] = {}
        self._lock = threading.Lock()

    def get_or_defer[T](
        self,
        key: str,
        factory: Callable[[], Awaitable[T]],
        *,
        ttl: float | None = None,
    ) -> T | Awaitable[T]:
        """Return a cached value if fresh, otherwise an awaitable for *factory*.

        ``ttl=None`` uses the cache default. ``ttl <= 0`` bypasses both storage
        and in-flight dedupe, which is useful when a caller wants Suspense
        deferral without reuse. Exceptions are never cached.
        """
        if not key:
            msg = "DeferredCache key must be a non-empty string."
            raise ValueError(msg)

        ttl_value = self._default_ttl if ttl is None else float(ttl)
        if ttl_value <= 0:
            return _resolve_uncached(factory)

        now = time.monotonic()
        with self._lock:
            entry = self._data.get(key)
            if entry is not None:
                if entry.expires_at > now:
                    return cast(T, entry.value)
                self._data.pop(key, None)

            inflight = self._inflight.get(key)
            if inflight is not None:
                return cast(Awaitable[T], inflight)

            shared = _SharedDeferred(self, key, factory, ttl_value)
            self._inflight[key] = shared
            return shared

    def delete(self, key: str) -> None:
        """Remove a cached or in-flight value if present."""
        with self._lock:
            self._data.pop(key, None)
            self._inflight.pop(key, None)

    def clear(self) -> None:
        """Remove all cached and in-flight values."""
        with self._lock:
            self._data.clear()
            self._inflight.clear()

    def _store_success[T](
        self,
        key: str,
        value: T,
        ttl: float,
        shared: _SharedDeferred[Any],
    ) -> None:
        expires_at = time.monotonic() + ttl
        with self._lock:
            if self._inflight.get(key) is shared:
                self._data[key] = _CachedValue(value, expires_at)
                self._inflight.pop(key, None)

    def _discard_inflight(self, key: str, shared: _SharedDeferred[Any]) -> None:
        with self._lock:
            if self._inflight.get(key) is shared:
                self._inflight.pop(key, None)
