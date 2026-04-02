"""Chirp caching framework.

Three levels of caching:
1. Per-view: ``@cache_view(ttl=300)``
2. Site-wide: ``CacheMiddleware`` (opt-in)
3. Template fragment: ``{% cache "key" ttl %}...{% endcache %}``

Usage::

    from chirp.cache import get_cache, cache_view

    @app.route("/products")
    @cache_view(ttl=300)
    async def products():
        return await db.fetch(Product, "SELECT * FROM products")

    # Low-level
    cache = get_cache()
    await cache.set("key", b"value", ttl=600)
"""

import functools
import logging
from collections.abc import Callable
from contextvars import ContextVar
from typing import Any

from chirp.cache.protocol import CacheBackend

__all__ = ["CacheBackend", "cache_view", "create_backend", "get_cache", "set_cache"]

logger = logging.getLogger("chirp.cache")

_cache_var: ContextVar[CacheBackend | None] = ContextVar("chirp_cache", default=None)


def get_cache() -> CacheBackend | None:
    """Return the current cache backend. None if no cache configured."""
    return _cache_var.get()


def set_cache(backend: CacheBackend) -> None:
    """Set the cache backend for the current context."""
    _cache_var.set(backend)


def create_backend(name: str, **kwargs: Any) -> CacheBackend:
    """Create a cache backend by name."""
    if name == "memory":
        from chirp.cache.backends.memory import MemoryCacheBackend

        return MemoryCacheBackend()
    elif name == "redis":
        from chirp.cache.backends.redis import RedisCacheBackend

        return RedisCacheBackend(**kwargs)
    elif name == "null":
        from chirp.cache.backends.null import NullCacheBackend

        return NullCacheBackend()
    msg = f"Unknown cache backend: {name!r}. Use 'memory', 'redis', or 'null'."
    raise ValueError(msg)


def cache_view(ttl: int = 300, key_func: Callable[..., str] | None = None) -> Callable:
    """Decorator to cache a view's response.

    Usage::

        @app.route("/products")
        @cache_view(ttl=300)
        async def products():
            ...
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            backend = get_cache()
            if backend is None:
                return await func(*args, **kwargs)

            # Build cache key from function name and args
            if key_func is not None:
                cache_key = key_func(*args, **kwargs)
            else:
                cache_key = f"chirp:view:{func.__module__}.{getattr(func, '__qualname__', getattr(func, '__name__', 'unknown'))}"

            try:
                cached = await backend.get(cache_key)
            except Exception:
                logger.warning("Cache get error in @cache_view", exc_info=True)
                cached = None

            if cached is not None:
                from chirp.http.response import Response

                return Response(
                    cached.decode("utf-8", errors="replace"),
                    status=200,
                    content_type="text/html",
                )

            result = await func(*args, **kwargs)

            # Cache the result if it's a Response
            from chirp.http.response import Response

            if isinstance(result, Response) and result.status == 200:
                try:
                    body = result.body
                    if isinstance(body, str):
                        body = body.encode("utf-8")
                    await backend.set(cache_key, body, ttl)
                except Exception:
                    logger.warning("Cache set error in @cache_view", exc_info=True)

            return result

        return wrapper

    return decorator
