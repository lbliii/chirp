"""Keyed rate limiting middleware.

Provides a small in-memory limiter intended for authentication endpoints
like login and password reset, and — via ``key_fn`` plus open path targeting
— any route or route group (per-user, per-resource, per-tenant). Supports
pluggable backends (the :class:`RateLimitBackend` Protocol) for Redis-backed
rate limiting across workers.

The plain default 429 body is text. Set ``error_template`` (and optionally
``error_block``) to render a self-contained HTML 429 for htmx form-action
POSTs — the middleware renders the template/block to a ``Response`` itself
(middleware returns ``AnyResponse``, never a Chirp return type), so the
over-limit case stays decoupled from the handler's negotiation path.
"""

import threading
import time
from collections.abc import Callable
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
    """Configuration for keyed rate limiting.

    Defaults target the common auth endpoints keyed by trusted client IP.
    Set ``paths=()`` to limit *all* matching-method routes, and supply
    ``key_fn`` to key on a per-user / per-resource / per-tenant identity
    instead of the client IP.
    """

    requests: int = 10
    window_seconds: int = 60
    block_seconds: int = 300
    methods: tuple[str, ...] = ("POST",)
    # paths gates which routes the limiter fires on. An EMPTY tuple means
    # "every route" (subject to ``methods``), so the limiter can target an
    # arbitrary route or group rather than only the auth path prefix.
    paths: tuple[str, ...] = ("/login", "/signup", "/register", "/password-reset")
    # key_header names a TRUSTED, server-set identity header (e.g. an
    # authenticated API-key header) to key the limiter on. It is consumed
    # verbatim — it is NOT an X-Forwarded-For override and is NOT comma-split,
    # because the first hop of a client-supplied XFF chain is spoofable. When
    # unset (or the header is absent), keying falls back to the fail-closed
    # trusted-proxy-corrected client IP (``request.trusted_client_ip``).
    key_header: str | None = None
    # key_fn computes the rate-limit bucket key for a request. It takes
    # precedence over key_header / trusted-IP keying when set. Return a
    # non-empty ``str`` to key on it, or ``None`` to SKIP rate-limiting this
    # request entirely (an explicit per-request opt-out — e.g. don't limit
    # already-authenticated trusted callers). SECURITY: derive the key from a
    # server-side identity (``request.user.id``, ``request.trusted_client_ip``,
    # a route param resolved against server records), never from a
    # client-controlled value a caller could rotate to dodge its own bucket.
    key_fn: Callable[[Request], str | None] | None = None
    # error_template / error_block opt into a self-contained HTML 429 body
    # rendered by the middleware for htmx requests. When error_template is set
    # and the over-limit request is htmx, the named block (or the whole
    # template) is rendered to the 429 Response body; otherwise the plain-text
    # "Too Many Requests" body is used. The block must exist in the template
    # (fail-loud BlockNotFoundError) — do not point at a missing block.
    error_template: str | None = None
    error_block: str | None = None
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
        # An empty ``paths`` tuple targets every route (method gate still
        # applies), letting the limiter cover an arbitrary route/group.
        if not self._config.paths:
            return True
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

        if cfg.key_fn is not None:
            key = cfg.key_fn(request)
            # An explicit per-request opt-out: ``None`` means "don't limit this
            # request" (e.g. trusted/authenticated callers).
            if key is None:
                return await next(request)
        else:
            key = self._identity_key(request)

        allowed, retry_after = await self._backend.check_and_update(
            key,
            time.time(),
            requests=cfg.requests,
            window_seconds=cfg.window_seconds,
            block_seconds=cfg.block_seconds,
        )
        if not allowed:
            return self._over_limit_response(request, retry_after)
        return await next(request)

    def _over_limit_response(self, request: Request, retry_after: int) -> Response:
        """Build the 429 response.

        For htmx requests with ``error_template`` configured, render a
        self-contained HTML body (the named ``error_block`` if set, else the
        whole template). Otherwise fall back to the plain-text body. Both
        carry ``Retry-After``. The render is done inside the middleware — it
        cannot return a Chirp ``Fragment`` and have ``negotiate_response`` run.
        """
        cfg = self._config
        headers = (("Retry-After", str(retry_after)),)
        error_template = cfg.error_template
        if error_template is not None and request.is_htmx:
            body = self._render_error_body(error_template, retry_after)
            if body is not None:
                return Response(status=429, body=body, headers=headers)
        return Response(status=429, body="Too Many Requests", headers=headers)

    def _render_error_body(self, error_template: str, retry_after: int) -> str | None:
        """Render ``error_template``/``error_block`` to HTML, or ``None``.

        Returns ``None`` (caller falls back to the plain body) only when no
        template environment is available for the request. A missing block is
        fail-loud (``BlockNotFoundError``) — configure a block that exists.
        """
        from chirp.templating.integration import get_active_kida_env

        env = get_active_kida_env()
        if env is None:
            return None
        template = env.get_template(error_template)
        context = {"retry_after": retry_after}
        error_block = self._config.error_block
        if error_block is not None:
            if error_block not in template.list_blocks():
                from chirp.errors import BlockNotFoundError

                raise BlockNotFoundError(template=error_template, block=error_block)
            return template.render_block(error_block, context)
        return template.render(context)
