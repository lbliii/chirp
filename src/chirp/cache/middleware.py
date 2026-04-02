"""Cache middleware — site-wide GET response caching.

Opt-in via ``cache_middleware_enabled = True`` in config.
Only caches GET requests that return 200 with no Set-Cookie header.
"""

import logging

from chirp.http.request import Request
from chirp.http.response import Response
from chirp.middleware.protocol import AnyResponse, Next

from .key import default_cache_key

logger = logging.getLogger("chirp.cache")


class CacheMiddleware:
    """Site-wide cache for GET 200 responses.

    Skips caching for:
    - Non-GET requests
    - Non-200 responses
    - Responses with Set-Cookie header
    - Streaming/SSE responses
    """

    __slots__ = ("_backend", "_key_func", "_ttl")

    def __init__(self, backend, ttl: int = 300, key_func=None) -> None:
        self._backend = backend
        self._ttl = ttl
        self._key_func = key_func or default_cache_key

    async def __call__(self, request: Request, next: Next) -> AnyResponse:
        if request.method != "GET":
            return await next(request)

        key = self._key_func(request)

        # Try cache
        try:
            cached = await self._backend.get(key)
        except Exception:
            logger.warning("Cache get error for %s", key, exc_info=True)
            cached = None

        if cached is not None:
            return Response(
                cached.decode("utf-8", errors="replace"),
                status=200,
                content_type="text/html",
            )

        response = await next(request)

        # Only cache Response (not streaming/SSE) with status 200
        if (
            isinstance(response, Response)
            and response.status == 200
            and not any(k.lower() == "set-cookie" for k, v in response.headers)
        ):
            try:
                body = response.body
                if isinstance(body, str):
                    body = body.encode("utf-8")
                await self._backend.set(key, body, self._ttl)
            except Exception:
                logger.warning("Cache set error for %s", key, exc_info=True)

        return response
