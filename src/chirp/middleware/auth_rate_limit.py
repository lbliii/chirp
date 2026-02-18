"""Auth-focused rate limiting middleware.

Provides a small in-memory limiter intended for authentication endpoints
like login and password reset.
"""

import threading
import time
from dataclasses import dataclass

from chirp.http.request import Request
from chirp.http.response import Response
from chirp.middleware.protocol import Next


@dataclass(frozen=True, slots=True)
class AuthRateLimitConfig:
    """Configuration for auth endpoint rate limiting."""

    requests: int = 10
    window_seconds: int = 60
    block_seconds: int = 300
    methods: tuple[str, ...] = ("POST",)
    paths: tuple[str, ...] = ("/login", "/signup", "/register", "/password-reset")
    key_header: str | None = "x-forwarded-for"


class AuthRateLimitMiddleware:
    """In-memory limiter for authentication-related endpoints."""

    __slots__ = ("_config", "_lock", "_state")

    def __init__(self, config: AuthRateLimitConfig | None = None) -> None:
        self._config = config or AuthRateLimitConfig()
        self._lock = threading.Lock()
        self._state: dict[str, tuple[int, float, float]] = {}

    def _path_matches(self, path: str) -> bool:
        return any(path == prefix or path.startswith(f"{prefix}/") for prefix in self._config.paths)

    def _identity_key(self, request: Request) -> str:
        header_name = self._config.key_header
        if header_name:
            raw = request.headers.get(header_name)
            if raw:
                # Respect standard comma-separated proxy chain, first hop is client.
                forwarded = raw.split(",")[0].strip()
                if forwarded:
                    return forwarded
        if request.client:
            return request.client[0]
        return "unknown"

    def _check_and_update(self, key: str, now: float) -> tuple[bool, int]:
        cfg = self._config
        with self._lock:
            count, window_start, blocked_until = self._state.get(key, (0, now, 0.0))
            if blocked_until > now:
                retry_after = max(1, int(blocked_until - now))
                return False, retry_after

            if now - window_start >= cfg.window_seconds:
                count = 0
                window_start = now

            count += 1
            if count > cfg.requests:
                blocked_until = now + cfg.block_seconds
                self._state[key] = (count, window_start, blocked_until)
                return False, cfg.block_seconds

            self._state[key] = (count, window_start, 0.0)
            return True, 0

    async def __call__(self, request: Request, next: Next) -> Response:
        cfg = self._config
        if request.method not in cfg.methods or not self._path_matches(request.path):
            return await next(request)

        key = self._identity_key(request)
        allowed, retry_after = self._check_and_update(key, time.time())
        if not allowed:
            return Response(
                status=429,
                body="Too Many Requests",
                headers=(("Retry-After", str(retry_after)),),
            )
        return await next(request)
