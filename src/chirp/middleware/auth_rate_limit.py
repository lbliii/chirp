"""Auth-focused rate limiting middleware.

Provides a small in-memory limiter intended for authentication endpoints
like login and password reset. Supports pluggable backends for Redis-backed
rate limiting across workers.
"""

import threading
import time
from dataclasses import dataclass
from typing import Protocol

from chirp.http.request import Request
from chirp.http.response import Response
from chirp.middleware.protocol import AnyResponse, Next


class RateLimitBackend(Protocol):
    """Protocol for rate limit storage backends."""

    async def check_and_update(
        self,
        key: str,
        now: float,
        *,
        requests: int,
        window_seconds: int,
        block_seconds: int,
    ) -> tuple[bool, int]:
        """Check if allowed, increment, and optionally block. Returns (allowed, retry_after)."""
        ...


@dataclass(frozen=True, slots=True)
class AuthRateLimitConfig:
    """Configuration for auth endpoint rate limiting."""

    requests: int = 10
    window_seconds: int = 60
    block_seconds: int = 300
    methods: tuple[str, ...] = ("POST",)
    paths: tuple[str, ...] = ("/login", "/signup", "/register", "/password-reset")
    # key_header names a TRUSTED, server-set identity header (e.g. an
    # authenticated API-key header) to key the limiter on. It is consumed
    # verbatim — it is NOT an X-Forwarded-For override and is NOT comma-split,
    # because the first hop of a client-supplied XFF chain is spoofable. When
    # unset (or the header is absent), keying falls back to the fail-closed
    # trusted-proxy-corrected client IP (``request.trusted_client_ip``).
    key_header: str | None = None
    backend: RateLimitBackend | None = None  # None = in-memory


def redis_rate_limit_backend(
    redis_url: str, key_prefix: str = "chirp:ratelimit:"
) -> RateLimitBackend:
    """Create a Redis-backed rate limit backend. Requires ``pip install chirp[redis]``."""
    from chirp.middleware._redis_rate_limit import RedisRateLimitBackend

    return RedisRateLimitBackend(redis_url, key_prefix)


class _InMemoryRateLimitBackend:
    """In-memory rate limit backend."""

    __slots__ = ("_lock", "_state")

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state: dict[str, tuple[int, float, float]] = {}

    async def check_and_update(
        self,
        key: str,
        now: float,
        *,
        requests: int,
        window_seconds: int,
        block_seconds: int,
    ) -> tuple[bool, int]:
        with self._lock:
            count, window_start, blocked_until = self._state.get(key, (0, now, 0.0))
            if blocked_until > now:
                return False, max(1, int(blocked_until - now))
            if now - window_start >= window_seconds:
                count = 0
                window_start = now
            count += 1
            if count > requests:
                self._state[key] = (count, window_start, now + block_seconds)
                return False, block_seconds
            self._state[key] = (count, window_start, 0.0)
            return True, 0


class AuthRateLimitMiddleware:
    """Rate limiter for authentication-related endpoints."""

    __slots__ = ("_backend", "_config")

    def __init__(self, config: AuthRateLimitConfig | None = None) -> None:
        self._config = config or AuthRateLimitConfig()
        self._backend = self._config.backend or _InMemoryRateLimitBackend()

    def _path_matches(self, path: str) -> bool:
        return any(path == prefix or path.startswith(f"{prefix}/") for prefix in self._config.paths)

    def _identity_key(self, request: Request) -> str:
        header_name = self._config.key_header
        if header_name:
            # key_header must name a TRUSTED, server-set identity header. It is
            # consumed verbatim — no first-comma split — so a spoofable
            # client-supplied chain (e.g. X-Forwarded-For) cannot be used to
            # rotate identities and evade the limit.
            raw = request.headers.get(header_name)
            if raw:
                identity = raw.strip()
                if identity:
                    return identity
        # Fail-closed default: the trusted-proxy-corrected client IP. Raw
        # X-Forwarded-For is never trusted here.
        return request.trusted_client_ip

    async def __call__(self, request: Request, next: Next) -> AnyResponse:
        cfg = self._config
        if request.method not in cfg.methods or not self._path_matches(request.path):
            return await next(request)

        key = self._identity_key(request)
        cfg = self._config
        allowed, retry_after = await self._backend.check_and_update(
            key,
            time.time(),
            requests=cfg.requests,
            window_seconds=cfg.window_seconds,
            block_seconds=cfg.block_seconds,
        )
        if not allowed:
            return Response(
                status=429,
                body="Too Many Requests",
                headers=(("Retry-After", str(retry_after)),),
            )
        return await next(request)
