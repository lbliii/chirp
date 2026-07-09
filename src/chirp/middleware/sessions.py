"""Session middleware — signed cookie and Redis-backed sessions.

Session data is stored via a pluggable ``SessionStore``. Default is
``CookieSessionStore`` (signed cookie with itsdangerous). For
horizontal scaling, use ``RedisSessionStore``.

Cookies are signed with HMAC-SHA-256 by default (configurable via
``SessionConfig.signer_digest``). A SHA-1 fallback signer keeps cookies
issued by older releases (itsdangerous' historical default) readable, so
upgrading does not log every existing user out.

The session object is stored in a ContextVar, accessible via
``get_session()`` from any handler or middleware.

``itsdangerous`` is required for cookie store. ``redis`` is required
for RedisSessionStore (``pip install chirp[redis]``).
"""

import hashlib
import logging
from collections.abc import Mapping
from contextvars import ContextVar
from dataclasses import dataclass
from time import time
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, ClassVar, Literal, Protocol

from itsdangerous import BadData

from chirp.errors import ConfigurationError
from chirp.http.request import Request
from chirp.middleware.protocol import AnyResponse, Next

_log = logging.getLogger("chirp.sessions")

if TYPE_CHECKING:
    pass


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


# Empty read-only session view returned by the template-safe ``session()``
# global when no SessionMiddleware is active. A shared MappingProxyType keeps
# templates from accidentally mutating a throwaway dict (writes would be lost),
# and avoids allocating per render.
_EMPTY_SESSION: Mapping[str, Any] = MappingProxyType({})


def session() -> Mapping[str, Any]:
    """Return the current session for templates — never raises.

    Template-friendly counterpart to ``get_session()``. Returns the live
    session dict when ``SessionMiddleware`` is active, or an empty read-only
    mapping otherwise (mirroring ``current_user()``'s never-raise contract, so
    a template rendered without a session does not blow up)::

        {% if session().get("flash") %}
            <div class="flash">{{ session()["flash"] }}</div>
        {% endif %}

    Use the imperative ``get_session()`` (which raises ``LookupError`` without
    ``SessionMiddleware``) from handlers where the session is required.
    """
    active = _session_var.get()
    if active is None:
        return _EMPTY_SESSION
    return active


@dataclass(slots=True)
class _RegenerationState:
    """Mutable request-local state shared with sync handler context copies."""

    requested: bool = False
    old_id: str | None = None


_regeneration_state_var: ContextVar[_RegenerationState | None] = ContextVar(
    "chirp_regeneration_state", default=None
)


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
    regeneration_state = _regeneration_state_var.get()
    if regeneration_state is not None:
        regeneration_state.requested = True
        regeneration_state.old_id = old_id
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
    secure: bool | Literal["auto"] = "auto"
    httponly: bool = True
    samesite: str = "lax"
    signer_digest: Literal["sha256", "sha512"] = "sha256"
    idle_timeout_seconds: int | None = None
    absolute_timeout_seconds: int | None = None
    created_at_key: str = "__created_at"
    last_seen_at_key: str = "__last_seen_at"
    store: SessionStore | None = None  # None = CookieSessionStore (default)


# Deployment environments that imply a secure (HTTPS) origin. ``"auto"``
# resolves ``secure=True`` for these and ``False`` everywhere else. This mirrors
# the secret_key env gate and the rules_security_stack severity matrix:
# ``env`` is the single posture signal — NOT request scheme or ``ssl_certfile``
# (which is set in local HTTPS dev and would otherwise silently log dev users
# out when the cookie is sent over a non-secure mixed-content path).
_SECURE_ENVS = frozenset({"production", "staging"})


def resolve_cookie_secure(secure: bool | Literal["auto"], *, env: str) -> bool:
    """Resolve a (possibly ``"auto"``) ``SessionConfig.secure`` to a concrete bool.

    An explicit ``bool`` is returned unchanged — the app author opted in or out
    deliberately. ``"auto"`` returns ``True`` iff ``env`` is a secure-origin
    deployment environment (``"production"`` / ``"staging"``) and ``False``
    otherwise (notably local development), so a default-config app over HTTPS in
    production ships ``Secure`` session cookies without the author touching the
    field.

    ``env`` is the sole posture signal: this resolver deliberately does NOT key
    off ``ssl_certfile`` or request scheme, because local HTTPS dev sets
    ``ssl_certfile`` yet must keep ``secure=False`` to avoid logging dev users
    out.
    """
    if secure is True or secure is False:
        return secure
    return env in _SECURE_ENVS


def _secure_for_cookie(secure: bool | Literal["auto"]) -> bool:
    """Narrow a (resolved) ``secure`` to ``bool`` for ``with_cookie``.

    ``resolve_secure`` runs at freeze, so by request time ``secure`` is always a
    concrete ``bool``. This guard makes that invariant statically true at the
    ``with_cookie`` call site (which is typed ``bool``) and fails safe to
    ``False`` — the non-secure / development posture — for the impossible case
    where resolution did not run, rather than emitting a stringly ``"auto"``.
    """
    return secure if isinstance(secure, bool) else False


# -- Store implementations --


class CookieSessionStore:
    """Signed cookie session store. Session data stored in cookie."""

    __slots__ = ("_config", "_configured_secure", "_serializer")

    def __init__(self, config: SessionConfig) -> None:
        try:
            from itsdangerous import URLSafeTimedSerializer
        except ImportError:
            msg = (
                "CookieSessionStore requires 'itsdangerous'. Install with: pip install itsdangerous"
            )
            raise ConfigurationError(msg) from None
        if not config.secret_key:
            msg = (
                "SessionConfig.secret_key must not be empty. "
                "Pass SessionConfig(secret_key=app.config.secret_key) or set "
                "AppConfig(secret_key=...) / CHIRP_SECRET_KEY before adding SessionMiddleware."
            )
            raise ConfigurationError(msg)
        # Resolve the configured digest via an explicit allowlist — never a
        # stringly ``getattr(hashlib, ...)`` lookup. Fail loud at construction.
        digest_methods = {"sha256": hashlib.sha256, "sha512": hashlib.sha512}
        digest = digest_methods.get(config.signer_digest)
        if digest is None:
            msg = (
                f"SessionConfig.signer_digest must be one of "
                f"{sorted(digest_methods)}, got {config.signer_digest!r}."
            )
            raise ConfigurationError(msg)
        self._config = config
        # Preserve the originally-configured secure value ("auto" | bool) before
        # freeze resolution mutates _config. Contract checks re-resolve THIS
        # against the posture env so --deploy evaluates the app as it would be in
        # production, not the dev-resolved bool (which would burn the "auto"
        # sentinel and false-ERROR a deploy-ready default).
        self._configured_secure = config.secure
        # Sign new cookies with the configured (SHA-256+) digest. Keep a SHA-1
        # fallback signer so cookies issued by older releases (itsdangerous'
        # historical default) still verify and load.
        self._serializer = URLSafeTimedSerializer(
            config.secret_key,
            signer_kwargs={"digest_method": digest},
            fallback_signers=[{"digest_method": hashlib.sha1}],
        )

    def resolve_secure(self, env: str) -> None:
        """Resolve ``config.secure`` (``"auto"`` -> bool) for *env*, in place.

        Called once at freeze. ``save()`` passes ``cfg.secure`` straight to
        ``with_cookie`` (typed ``bool``), so the cached config must never hold
        the string ``"auto"`` at request time. The serializer does not depend on
        ``secure``, so no rebuild is needed — only the frozen config is swapped.
        """
        from dataclasses import replace

        self._config = replace(
            self._config, secure=resolve_cookie_secure(self._config.secure, env=env)
        )

    async def load(self, request: Request) -> dict[str, Any]:
        cookie_value = request.cookies.get(self._config.cookie_name)
        if not cookie_value:
            return {}
        try:
            data = self._serializer.loads(cookie_value, max_age=self._config.max_age)
        except BadData:
            # BadData covers tamper (BadSignature), expiry (SignatureExpired),
            # and malformed tokens — a fresh empty session is the correct
            # fail-safe. Any OTHER exception (a real bug or library break)
            # must propagate rather than be silently swallowed.
            _log.debug(
                "Failed to deserialize session cookie %r; starting fresh session",
                self._config.cookie_name,
                exc_info=True,
            )
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
            secure=_secure_for_cookie(cfg.secure),
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
        except TypeError, ValueError:
            _log.debug(
                "Session timeout timestamps invalid; discarding session",
                exc_info=True,
            )
            return {}
        if (
            cfg.absolute_timeout_seconds is not None
            and now - created_ts > cfg.absolute_timeout_seconds
        ):
            return {}
        if cfg.idle_timeout_seconds is not None and now - last_seen_ts > cfg.idle_timeout_seconds:
            return {}
        return data


class RedisSessionStore:
    """Redis-backed session store. Cookie stores session ID only."""

    __slots__ = ("_config", "_configured_secure", "_prefix", "_redis_url")

    def __init__(
        self,
        config: SessionConfig,
        redis_url: str,
        key_prefix: str = "chirp:session:",
    ) -> None:
        import importlib.util

        if importlib.util.find_spec("redis.asyncio") is None:
            raise ConfigurationError(
                "RedisSessionStore requires 'redis'. Install with: pip install chirp[redis]"
            ) from None
        if not config.secret_key:
            msg = "SessionConfig.secret_key must not be empty."
            raise ConfigurationError(msg)
        self._config = config
        # Preserve the originally-configured secure value (see CookieSessionStore).
        self._configured_secure = config.secure
        self._redis_url = redis_url
        self._prefix = key_prefix

    def resolve_secure(self, env: str) -> None:
        """Resolve ``config.secure`` (``"auto"`` -> bool) for *env*, in place.

        Mirror of ``CookieSessionStore.resolve_secure``: ``save()`` passes
        ``cfg.secure`` straight to ``with_cookie`` (typed ``bool``), so the
        cached config must hold a concrete bool by request time.
        """
        from dataclasses import replace

        self._config = replace(
            self._config, secure=resolve_cookie_secure(self._config.secure, env=env)
        )

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
        except json.JSONDecodeError, TypeError:
            _log.debug(
                "Failed to decode Redis session; starting fresh session",
                exc_info=True,
            )
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
            secure=_secure_for_cookie(cfg.secure),
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
        except TypeError, ValueError:
            _log.debug(
                "Session timeout timestamps invalid; discarding session",
                exc_info=True,
            )
            return {}
        if (
            cfg.absolute_timeout_seconds is not None
            and now - created_ts > cfg.absolute_timeout_seconds
        ):
            return {}
        if cfg.idle_timeout_seconds is not None and now - last_seen_ts > cfg.idle_timeout_seconds:
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

    __slots__ = ("_config", "_configured_secure", "_store")

    # Template globals auto-registered by the AppCompiler when this middleware
    # is present (it scans every registered middleware for ``.template_globals``;
    # see ``src/chirp/app/compiler.py``). Mirrors ``AuthMiddleware.template_globals``.
    template_globals: ClassVar[dict[str, Any]] = {
        "session": session,
    }

    def __init__(self, config: SessionConfig) -> None:
        self._config = config
        self._configured_secure = config.secure
        self._store = config.store or CookieSessionStore(config)

    @property
    def configured_secure(self) -> bool | Literal["auto"]:
        """The ``secure`` value as originally configured (``"auto"`` | bool).

        Unlike :attr:`secure` (the freeze-resolved concrete bool), this is the
        *unresolved* value, so a contract check can re-resolve it against a
        posture env. That is what lets ``app.check(deploy=True)`` evaluate a
        blessed-default ``secure="auto"`` app as it WOULD be in production
        (resolves Secure → clean) instead of the dev-resolved ``False`` (a false
        ERROR). Prefers the store's captured value (authoritative for the
        two-config pattern); falls back to this middleware's own.
        """
        store_configured = getattr(self._store, "_configured_secure", None)
        if store_configured is not None:
            return store_configured
        return self._configured_secure

    @property
    def secure(self) -> bool | Literal["auto"]:
        """Effective ``secure`` value of the cookie this middleware emits.

        Reads the **store's** config (the store owns the cookie attributes at
        ``save`` time, which matters for the two-config pattern where a user
        passes ``SessionConfig(store=RedisSessionStore(SessionConfig(...), ...))``
        — the inner config is authoritative). Lets contract checks read the
        effective value without reaching into private slots across store types.
        After ``resolve_secure`` runs at freeze this is a concrete ``bool``;
        before freeze it may still be ``"auto"``.
        """
        store_config = getattr(self._store, "_config", None)
        if store_config is not None:
            return store_config.secure
        return self._config.secure

    def resolve_secure(self, env: str) -> None:
        """Resolve ``secure`` (``"auto"`` -> bool) for *env* across configs.

        Called once at freeze (see ``AppCompiler``). Resolves this middleware's
        own ``_config`` AND the store's cached config. For the two-config
        pattern — a user passes ``config.store=RedisSessionStore(SessionConfig(
        secure="auto"), ...)`` — the store carries its OWN inner ``SessionConfig``
        that ``save()`` reads, so it must be resolved independently. A custom
        store that does not implement ``resolve_secure`` is left untouched (it
        owns its own cookie policy).
        """
        from dataclasses import replace

        self._config = replace(
            self._config, secure=resolve_cookie_secure(self._config.secure, env=env)
        )
        store_resolve = getattr(self._store, "resolve_secure", None)
        if callable(store_resolve):
            store_resolve(env)

    async def __call__(self, request: Request, next: Next) -> AnyResponse:
        """Load session, dispatch, then save session to response."""
        store_config = getattr(self._store, "_config", None)
        cookie_name = getattr(store_config, "cookie_name", self._config.cookie_name)
        had_session_cookie = cookie_name in request.cookies
        session = await self._store.load(request)
        if (
            self._config.idle_timeout_seconds is not None
            or self._config.absolute_timeout_seconds is not None
        ):
            now = time()
            session.setdefault(self._config.created_at_key, now)
            session[self._config.last_seen_at_key] = now
        token = _session_var.set(session)
        regeneration_state = _RegenerationState()
        regeneration_token = _regeneration_state_var.set(regeneration_state)

        try:
            try:
                response = await next(request)
            finally:
                _session_var.reset(token)

            if not had_session_cookie and not session and not regeneration_state.requested:
                return response
            return await self._store.save(
                response,
                session,
                regenerate_old_id=regeneration_state.old_id,
            )
        finally:
            _regeneration_state_var.reset(regeneration_token)
