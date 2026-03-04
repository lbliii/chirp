"""Session middleware — signed cookie and Redis-backed sessions.

Session data is stored via a pluggable ``SessionStore``. Default is
``CookieSessionStore`` (signed cookie with itsdangerous). For
horizontal scaling, use ``RedisSessionStore``.

The session object is stored in a ContextVar, accessible via
``get_session()`` from any handler or middleware.

``itsdangerous`` is required for cookie store. ``redis`` is required
for RedisSessionStore (``pip install chirp[redis]``).
"""

from contextvars import ContextVar
from dataclasses import dataclass
from time import time
from typing import TYPE_CHECKING, Any, Protocol

from chirp.errors import ConfigurationError
from chirp.http.request import Request
from chirp.middleware.protocol import AnyResponse, Next

if TYPE_CHECKING:
    from collections.abc import Awaitable


class SessionStore(Protocol):
    """Protocol for session storage backends."""

    async def load(self, request: Request) -> dict[str, Any]:
        """Load session data from the store. Returns empty dict if none."""
        ...

    async def save(
        self,
        response: AnyResponse,
        session: dict[str, Any],
        *,
        regenerate_old_id: str | None = None,
    ) -> AnyResponse:
        """Persist session and return response with cookie/headers.

        When regenerate_old_id is set, the store should create a new
        session and delete the old one (for Redis).
        """
        ...

# -- Session ContextVar --

_session_var: ContextVar[dict[str, Any] | None] = ContextVar("chirp_session", default=None)


def get_session() -> dict[str, Any]:
    """Return the current session dict.

    Raises ``LookupError`` if called outside a request with
    ``SessionMiddleware`` active.
    """
    session = _session_var.get()
    if session is None:
        msg = (
            "No active session. Ensure SessionMiddleware is added "
            "to the app before accessing the session."
        )
        raise LookupError(msg)
    return session


_regenerate_var: ContextVar[str | None] = ContextVar("chirp_regenerate_old_id", default=None)


def regenerate_session() -> dict[str, Any]:
    """Clear the session and return a fresh empty dict.

    Prevents session fixation by discarding all data from the
    previous session. For cookie store, re-signs empty dict.
    For Redis store, creates new session ID and deletes old.

    Called automatically by ``login()`` and ``logout()``. Can also
    be called directly when you need to rotate the session::

        from chirp.middleware.sessions import regenerate_session

        regenerate_session()  # old data gone, new cookie on response

    Raises ``LookupError`` if called outside a request with
    ``SessionMiddleware`` active.
    """
    session = get_session()
    old_id = session.get("__session_id")
    session.clear()
    _regenerate_var.set(old_id)
    return session


# -- Configuration --


@dataclass(frozen=True, slots=True)
class SessionConfig:
    """Session middleware configuration.

    ``secret_key`` is required for cookie signing. When using
    ``RedisSessionStore``, the cookie stores only the session ID.
    """

    secret_key: str
    cookie_name: str = "chirp_session"
    max_age: int = 86400  # 24 hours
    path: str = "/"
    domain: str | None = None
    secure: bool = False
    httponly: bool = True
    samesite: str = "lax"
    idle_timeout_seconds: int | None = None
    absolute_timeout_seconds: int | None = None
    created_at_key: str = "__created_at"
    last_seen_at_key: str = "__last_seen_at"
    store: SessionStore | None = None  # None = CookieSessionStore (default)


# -- Store implementations --


class CookieSessionStore:
    """Signed cookie session store. Session data stored in cookie."""

    __slots__ = ("_config", "_serializer")

    def __init__(self, config: SessionConfig) -> None:
        try:
            from itsdangerous import URLSafeTimedSerializer
        except ImportError:
            msg = (
                "CookieSessionStore requires 'itsdangerous'. "
                "Install with: pip install itsdangerous"
            )
            raise ConfigurationError(msg) from None
        if not config.secret_key:
            msg = "SessionConfig.secret_key must not be empty."
            raise ConfigurationError(msg)
        self._config = config
        self._serializer = URLSafeTimedSerializer(config.secret_key)

    async def load(self, request: Request) -> dict[str, Any]:
        cookie_value = request.cookies.get(self._config.cookie_name)
        if not cookie_value:
            return {}
        try:
            data = self._serializer.loads(cookie_value, max_age=self._config.max_age)
        except Exception:
            return {}
        if not isinstance(data, dict):
            return {}
        return self._apply_timeouts(data)

    async def save(
        self,
        response: AnyResponse,
        session: dict[str, Any],
        *,
        regenerate_old_id: str | None = None,
    ) -> AnyResponse:
        cfg = self._config
        value = self._serializer.dumps(session)
        return response.with_cookie(
            name=cfg.cookie_name,
            value=value,
            max_age=cfg.max_age,
            path=cfg.path,
            domain=cfg.domain,
            secure=cfg.secure,
            httponly=cfg.httponly,
            samesite=cfg.samesite,
        )

    def _apply_timeouts(self, data: dict[str, Any]) -> dict[str, Any]:
        cfg = self._config
        if cfg.idle_timeout_seconds is None and cfg.absolute_timeout_seconds is None:
            return data
        now = time()
        created_at = data.get(cfg.created_at_key, now)
        last_seen_at = data.get(cfg.last_seen_at_key, now)
        try:
            created_ts = float(created_at)
            last_seen_ts = float(last_seen_at)
        except (TypeError, ValueError):
            return {}
        if (
            cfg.absolute_timeout_seconds is not None
            and now - created_ts > cfg.absolute_timeout_seconds
        ):
            return {}
        if (
            cfg.idle_timeout_seconds is not None
            and now - last_seen_ts > cfg.idle_timeout_seconds
        ):
            return {}
        return data


class RedisSessionStore:
    """Redis-backed session store. Cookie stores session ID only."""

    __slots__ = ("_config", "_redis_url", "_prefix")

    def __init__(
        self,
        config: SessionConfig,
        redis_url: str,
        key_prefix: str = "chirp:session:",
    ) -> None:
        try:
            import redis.asyncio
        except ImportError:
            msg = (
                "RedisSessionStore requires 'redis'. "
                "Install with: pip install chirp[redis]"
            )
            raise ConfigurationError(msg) from None
        if not config.secret_key:
            msg = "SessionConfig.secret_key must not be empty."
            raise ConfigurationError(msg)
        self._config = config
        self._redis_url = redis_url
        self._prefix = key_prefix

    async def load(self, request: Request) -> dict[str, Any]:
        import json

        import redis.asyncio as redis

        session_id = request.cookies.get(self._config.cookie_name)
        if not session_id:
            return {}
        client = redis.from_url(self._redis_url)
        try:
            raw = await client.get(self._prefix + session_id)
        finally:
            await client.aclose()
        if not raw:
            return {}
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}
        if not isinstance(data, dict):
            return {}
        data["__session_id"] = session_id
        return self._apply_timeouts(data)

    async def save(
        self,
        response: AnyResponse,
        session: dict[str, Any],
        *,
        regenerate_old_id: str | None = None,
    ) -> AnyResponse:
        import json
        import uuid

        import redis.asyncio as redis

        old_id = session.pop("__session_id", None) or regenerate_old_id
        if regenerate_old_id is not None or old_id is None:
            session_id = str(uuid.uuid4())
        else:
            session_id = old_id

        # Store only user data (exclude internal keys)
        to_store = {k: v for k, v in session.items() if not k.startswith("__")}
        client = redis.from_url(self._redis_url)
        try:
            key = self._prefix + session_id
            await client.setex(
                key,
                self._config.max_age,
                json.dumps(to_store),
            )
            if old_id is not None and old_id != session_id:
                await client.delete(self._prefix + old_id)
        finally:
            await client.aclose()

        cfg = self._config
        return response.with_cookie(
            name=cfg.cookie_name,
            value=session_id,
            max_age=cfg.max_age,
            path=cfg.path,
            domain=cfg.domain,
            secure=cfg.secure,
            httponly=cfg.httponly,
            samesite=cfg.samesite,
        )

    def _apply_timeouts(self, data: dict[str, Any]) -> dict[str, Any]:
        cfg = self._config
        if cfg.idle_timeout_seconds is None and cfg.absolute_timeout_seconds is None:
            return data
        now = time()
        created_at = data.get(cfg.created_at_key, now)
        last_seen_at = data.get(cfg.last_seen_at_key, now)
        try:
            created_ts = float(created_at)
            last_seen_ts = float(last_seen_at)
        except (TypeError, ValueError):
            return {}
        if (
            cfg.absolute_timeout_seconds is not None
            and now - created_ts > cfg.absolute_timeout_seconds
        ):
            return {}
        if (
            cfg.idle_timeout_seconds is not None
            and now - last_seen_ts > cfg.idle_timeout_seconds
        ):
            return {}
        return data


# -- Middleware --


class SessionMiddleware:
    """Session middleware with pluggable store (cookie or Redis).

    Uses ``CookieSessionStore`` by default. For horizontal scaling,
    pass ``RedisSessionStore`` via ``SessionConfig.store``.

    Usage::

        from chirp.middleware.sessions import SessionConfig, SessionMiddleware

        app.add_middleware(SessionMiddleware(SessionConfig(
            secret_key="my-secret-key",
        )))

        # Redis-backed (pip install chirp[redis]):
        from chirp.middleware.sessions import RedisSessionStore, SessionConfig

        app.add_middleware(SessionMiddleware(SessionConfig(
            secret_key="my-secret-key",
            store=RedisSessionStore(SessionConfig(secret_key="x"), "redis://localhost"),
        )))
    """

    __slots__ = ("_config", "_store")

    def __init__(self, config: SessionConfig) -> None:
        self._config = config
        self._store = config.store or CookieSessionStore(config)

    async def __call__(self, request: Request, next: Next) -> AnyResponse:
        """Load session, dispatch, then save session to response."""
        session = await self._store.load(request)
        if (
            self._config.idle_timeout_seconds is not None
            or self._config.absolute_timeout_seconds is not None
        ):
            now = time()
            session.setdefault(self._config.created_at_key, now)
            session[self._config.last_seen_at_key] = now
        token = _session_var.set(session)

        try:
            response = await next(request)
        finally:
            _session_var.reset(token)

        regenerate_old_id = _regenerate_var.get()
        try:
            _regenerate_var.set(None)
            return await self._store.save(
                response, session, regenerate_old_id=regenerate_old_id
            )
        finally:
            _regenerate_var.set(None)
