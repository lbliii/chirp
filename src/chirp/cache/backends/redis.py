"""Redis cache backend.

Requires ``redis`` (``pip install chirp[redis]``).
"""

from typing import Any


class RedisCacheBackend:
    """Redis-backed cache. Shared across workers.

    Usage::

        from chirp.cache.backends.redis import RedisCacheBackend
        backend = RedisCacheBackend("redis://localhost:6379/0")
    """

    __slots__ = ("_redis", "_url")

    def __init__(self, url: str = "redis://localhost:6379/0") -> None:
        self._url = url
        self._redis: Any = None

    async def connect(self) -> None:
        import redis.asyncio as aioredis

        self._redis = aioredis.from_url(self._url)

    async def disconnect(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None

    async def get(self, key: str) -> bytes | None:
        if self._redis is None:
            return None
        return await self._redis.get(key)

    async def set(self, key: str, value: bytes, ttl: int = 0) -> None:
        if self._redis is None:
            return
        if ttl > 0:
            await self._redis.setex(key, ttl, value)
        else:
            await self._redis.set(key, value)

    async def delete(self, key: str) -> None:
        if self._redis is None:
            return
        await self._redis.delete(key)

    async def clear(self) -> None:
        if self._redis is None:
            return
        await self._redis.flushdb()
