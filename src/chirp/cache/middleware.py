"""Cache middleware — site-wide GET response caching.

Opt-in via ``cache_middleware_enabled = True`` in config.
Only caches GET requests that return 200 with no Set-Cookie header.
Requests carrying Cookie or Authorization bypass the cache entirely.
"""

import base64
import json
import logging
from dataclasses import dataclass

from chirp.http.request import Request
from chirp.http.response import Response
from chirp.middleware.protocol import AnyResponse, Next

from .key import default_cache_key

logger = logging.getLogger("chirp.cache")
_CACHE_ENTRY_PREFIX = b"chirp-cache-v1\n"
_UNCACHEABLE_RESPONSE_HEADERS = frozenset(
    {
        "connection",
        "content-length",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }
)


@dataclass(frozen=True, slots=True)
class _CachedResponse:
    body: bytes
    content_type: str
    headers: tuple[tuple[str, str], ...]


class CacheMiddleware:
    """Site-wide cache for GET 200 responses.

    Skips caching for:
    - Non-GET requests
    - Requests with Cookie or Authorization headers
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
        if _has_private_request_headers(request):
            return await next(request)

        key = self._key_func(request)

        # Try cache
        try:
            cached = await self._backend.get(key)
        except Exception:
            logger.warning("Cache get error for %s", key, exc_info=True)
            cached = None

        if cached is not None:
            try:
                cached_response = _decode_cached_response(cached)
                return Response(
                    cached_response.body,
                    status=200,
                    content_type=cached_response.content_type,
                    headers=cached_response.headers,
                )
            except Exception:
                logger.warning("Cache decode error for %s", key, exc_info=True)

        response = await next(request)

        # Only cache Response (not streaming/SSE) with status 200 and no
        # Set-Cookie. Cookies arrive via two paths — ``with_cookie()`` writes
        # to ``response.cookies`` (flattened to Set-Cookie headers later by
        # sender.py); ``with_header("Set-Cookie", ...)`` writes to
        # ``response.headers`` directly. Both must skip caching, otherwise
        # one user's cookie would be replayed to others.
        if (
            isinstance(response, Response)
            and response.status == 200
            and not response.cookies
            and not any(k.lower() == "set-cookie" for k, v in response.headers)
        ):
            try:
                body = response.body
                if isinstance(body, str):
                    body = body.encode("utf-8")
                cached_response = _CachedResponse(
                    body=body,
                    content_type=response.content_type,
                    headers=_cacheable_response_headers(response.headers),
                )
                await self._backend.set(key, _encode_cached_response(cached_response), self._ttl)
            except Exception:
                logger.warning("Cache set error for %s", key, exc_info=True)

        return response


def _has_private_request_headers(request: Request) -> bool:
    """Return True for request headers that commonly vary per user."""
    return bool(request.headers.get("cookie") or request.headers.get("authorization"))


def _cacheable_response_headers(
    headers: tuple[tuple[str, str], ...],
) -> tuple[tuple[str, str], ...]:
    """Strip headers that the sender computes or that are hop-by-hop."""
    connection_tokens: set[str] = set()
    for name, value in headers:
        if name.lower() == "connection":
            connection_tokens.update(
                token.strip().lower() for token in value.split(",") if token.strip()
            )
    blocked = _UNCACHEABLE_RESPONSE_HEADERS | connection_tokens
    return tuple((name, value) for name, value in headers if name.lower() not in blocked)


def _encode_cached_response(response: _CachedResponse) -> bytes:
    payload = {
        "body": base64.b64encode(response.body).decode("ascii"),
        "content_type": response.content_type,
        "headers": list(response.headers),
    }
    return _CACHE_ENTRY_PREFIX + json.dumps(payload, separators=(",", ":")).encode("utf-8")


def _decode_cached_response(value: bytes) -> _CachedResponse:
    if not value.startswith(_CACHE_ENTRY_PREFIX):
        return _CachedResponse(
            body=value,
            content_type="text/html; charset=utf-8",
            headers=(),
        )
    payload = json.loads(value[len(_CACHE_ENTRY_PREFIX) :].decode("utf-8"))
    return _CachedResponse(
        body=base64.b64decode(payload["body"]),
        content_type=str(payload.get("content_type") or "text/html; charset=utf-8"),
        headers=_cacheable_response_headers(
            tuple((str(name), str(header_value)) for name, header_value in payload["headers"])
        ),
    )
