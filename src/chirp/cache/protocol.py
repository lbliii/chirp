"""Cache backend protocol — structural typing for cache stores."""

from typing import Protocol, runtime_checkable


@runtime_checkable
class CacheBackend(Protocol):
    """Protocol for cache backends.

    All methods are async. Values are bytes-based for backend flexibility.
    """

    async def get(self, key: str) -> bytes | None:
        """Get a cached value. Returns None on miss."""
        ...

    async def set(self, key: str, value: bytes, ttl: int = 0) -> None:
        """Set a cached value. ttl=0 means no expiration."""
        ...

    async def delete(self, key: str) -> None:
        """Delete a cached key."""
        ...

    async def clear(self) -> None:
        """Clear all cached entries."""
        ...
