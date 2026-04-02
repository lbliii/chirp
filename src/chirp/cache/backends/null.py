"""Null cache backend — no-op for testing and explicit opt-out."""


class NullCacheBackend:
    """No-op cache backend. All operations succeed without storing anything."""

    __slots__ = ()

    async def get(self, key: str) -> bytes | None:
        return None

    async def set(self, key: str, value: bytes, ttl: int = 0) -> None:
        pass

    async def delete(self, key: str) -> None:
        pass

    async def clear(self) -> None:
        pass
