"""Authentication middleware — dual-mode session + token auth.

Authenticates requests via session cookies (browsers) or bearer tokens
(API clients). The authenticated user is stored in a ContextVar,
accessible via ``get_user()`` from any handler or middleware.

Requires ``SessionMiddleware`` for session-based auth. Token auth
works independently.

Usage::

    from chirp.middleware.auth import AuthConfig, AuthMiddleware, get_user, login, logout
    from chirp.middleware.sessions import SessionConfig, SessionMiddleware

    app.add_middleware(SessionMiddleware(SessionConfig(secret_key="...")))
    app.add_middleware(AuthMiddleware(AuthConfig(
        load_user=my_load_user,       # async (id: str) -> User | None
        verify_token=my_verify_token, # async (token: str) -> User | None
    )))

    # In a handler:
    user = get_user()
    if user.is_authenticated:
        ...

    # Login/logout:
    await login(user)
    await logout()
"""

import logging
from collections.abc import Awaitable, Callable, Mapping
from contextvars import ContextVar, Token
from dataclasses import dataclass
from inspect import isawaitable
from typing import Any, ClassVar, Protocol, cast, runtime_checkable

from chirp.errors import ConfigurationError
from chirp.http.request import Request
from chirp.middleware.protocol import AnyResponse, Next
from chirp.security.audit import emit_security_event

_log = logging.getLogger("chirp.security")

# ---------------------------------------------------------------------------
# User protocols
# ---------------------------------------------------------------------------


@runtime_checkable
class User(Protocol):
    """Minimal user protocol.

    Any object with ``id`` and ``is_authenticated`` satisfies this.
    Developers bring their own user model — ORM class, dataclass, etc.
    """

    @property
    def id(self) -> str: ...

    @property
    def is_authenticated(self) -> bool: ...


@runtime_checkable
class UserWithPermissions(User, Protocol):
    """Extended user protocol with permission support.

    Used by ``@requires(*permissions)`` to check access.
    """

    @property
    def permissions(self) -> frozenset[str]: ...


# ---------------------------------------------------------------------------
# Token revocation store protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class TokenRevocationStore(Protocol):
    """Protocol for an app-supplied bearer-token revocation backend.

    The stateless bearer path (``verify_token``) has no built-in revocation:
    once a token verifies, it stays valid until it expires. A revocation store
    closes that gap — it is consulted **after** ``verify_token`` returns a user
    (token branch only) and gives two revocation axes that mirror how
    :attr:`AuthConfig.session_version` gives the session path mass revocation:

    - **per-token**: :meth:`is_token_revoked` rejects a single revoked ``jti``;
    - **per-user cutoff**: :meth:`user_revoked_at` rejects every token a user
      was issued before a ``revoked_at`` timestamp (token ``iat <= revoked_at``).

    Both axes require token claims, which Chirp does not decode itself — supply
    :attr:`AuthConfig.token_claims` to surface ``{jti, sub, iat}`` from the
    opaque token. With ``token_claims`` unset, only :meth:`is_token_revoked` can
    run (and only if the store is reachable without a ``jti``); the cutoff axis
    is skipped.

    The store is app-supplied and async. **Chirp holds no lock** — the store is
    responsible for its own concurrency (mirrors :class:`SessionStore`). On a
    store error Chirp **fails open** (treats the token as not revoked) and emits
    an ``auth.token.revocation_check_error`` security event, so a backend blip
    does not 401 every API client.
    """

    async def is_token_revoked(self, jti: str) -> bool:
        """Return ``True`` if the token with this ``jti`` has been revoked."""
        ...

    async def user_revoked_at(self, user_id: str) -> int | float | None:
        """Return a user's revocation-cutoff timestamp, or ``None`` if none.

        Tokens with ``iat <= revoked_at`` are rejected. ``None`` means the user
        has no cutoff (all their tokens remain valid).
        """
        ...


# ---------------------------------------------------------------------------
# AnonymousUser sentinel
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AnonymousUser:
    """Sentinel for unauthenticated requests.

    Returned by ``get_user()`` when no user is authenticated.
    Eliminates null checks — ``get_user()`` never returns ``None``.
    """

    id: str = ""
    is_authenticated: bool = False
    permissions: frozenset[str] = frozenset()


# ---------------------------------------------------------------------------
# User ContextVar
# ---------------------------------------------------------------------------

_ANONYMOUS: AnonymousUser = AnonymousUser()

_user_var: ContextVar[User] = ContextVar("chirp_user")


def _set_stream_user(user: User) -> Token[User]:
    """Re-establish the auth user while a streaming generator drains."""
    return _user_var.set(user)


def _reset_stream_user(token: Token[User]) -> None:
    _user_var.reset(token)


def get_user() -> User:
    """Return the current authenticated user (or ``AnonymousUser``).

    Raises ``LookupError`` if called outside a request with
    ``AuthMiddleware`` active.

    Inside an ``EventStream`` generator (SSE), this returns the user captured
    at **connect time**. SSE identity is pinned for the connection's lifetime:
    a user logged out or permission-revoked mid-stream keeps the connect-time
    identity until they reconnect. (Per-event revalidation is a deferred
    follow-up, not currently available.) An unauthenticated connection sees
    ``AnonymousUser`` for the whole stream.
    """
    try:
        return _user_var.get()
    except LookupError:
        msg = (
            "No auth context. Ensure AuthMiddleware is added to the app before accessing the user."
        )
        raise LookupError(msg) from None


# ---------------------------------------------------------------------------
# Login / Logout helpers
# ---------------------------------------------------------------------------

# Module-level reference to the active config, set by AuthMiddleware.__init__
_active_config: ContextVar[AuthConfig | None] = ContextVar("chirp_auth_config", default=None)


def login(user: User) -> None:
    """Log in a user — regenerate session, set user ID, update ContextVar.

    Regenerates the session to prevent session fixation attacks.
    Call from your login handler after verifying credentials::

        user = await verify_credentials(email, password)
        if user:
            login(user)
            return Redirect("/dashboard")

    Requires ``SessionMiddleware`` and ``AuthMiddleware`` to be active.
    """
    from chirp.middleware.sessions import regenerate_session

    config = _active_config.get()
    if config is None:
        msg = "login() requires AuthMiddleware to be active."
        raise LookupError(msg)

    session = regenerate_session()
    session[config.session_key] = user.id
    if config.session_version is not None:
        version = config.session_version(user)
        if version is not None:
            session[config.session_version_key] = str(version)
    _user_var.set(user)
    emit_security_event("auth.login.success", user_id=user.id)


def logout() -> None:
    """Log out the current user — regenerate session + clear ContextVar.

    Regenerates the session to discard all session data (not just the
    user ID). Call from your logout handler::

        logout()
        return Redirect("/")

    Requires ``SessionMiddleware`` and ``AuthMiddleware`` to be active.
    """
    from chirp.middleware.sessions import regenerate_session

    config = _active_config.get()
    if config is None:
        msg = "logout() requires AuthMiddleware to be active."
        raise LookupError(msg)

    regenerate_session()
    _user_var.set(_ANONYMOUS)
    emit_security_event("auth.logout.success")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AuthConfig:
    """Authentication middleware configuration.

    Attributes:
        session_key: Session dict key for the user ID.
        token_header: HTTP header for bearer tokens.
        token_scheme: Expected scheme prefix (e.g. ``"Bearer"``).
        load_user: Async callback to load a user by ID (session auth).
        verify_token: Async callback to verify a bearer token (token auth).
        login_url: URL to redirect unauthenticated browsers to.
            Set to ``None`` to disable redirects (return 401 instead).
        exclude_paths: Paths that skip authentication entirely.
        token_revocation_store: Optional :class:`TokenRevocationStore` consulted
            on the bearer path **after** ``verify_token`` returns a user. Unset
            (``None``) = today's behavior (no bearer-token revocation). Rejecting
            a token here returns an anonymous user and emits ``auth.token.revoked``.
        token_claims: Optional callback ``(token) -> Mapping`` (sync or async)
            returning at least ``jti`` (for :meth:`TokenRevocationStore.is_token_revoked`)
            and ``iat`` (for the :meth:`TokenRevocationStore.user_revoked_at`
            per-user cutoff). Chirp does not decode tokens itself; this is the
            claims seam that keeps ``verify_token`` an opaque ``(token) -> User``
            contract. Without it the store's per-user cutoff axis is skipped.
    """

    session_key: str = "user_id"
    token_header: str = "Authorization"  # noqa: S105
    token_scheme: str = "Bearer"  # noqa: S105
    load_user: Callable[[str], Awaitable[User | None]] | None = None
    verify_token: Callable[[str], Awaitable[User | None]] | None = None
    session_version: Callable[[User], str | int | None] | None = None
    session_version_key: str = "_session_version"
    login_url: str | None = "/login"
    exclude_paths: frozenset[str] = frozenset()
    token_revocation_store: TokenRevocationStore | None = None
    token_claims: Callable[[str], Mapping[str, Any] | Awaitable[Mapping[str, Any]]] | None = None


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------


def current_user() -> User:
    """Return the current user for templates.

    Template-friendly alias for ``get_user()``. Returns ``AnonymousUser``
    if no user is authenticated, never raises.

    Registered as a template global when ``AuthMiddleware`` is active::

        {% if current_user().is_authenticated %}
            <a href="/profile">{{ current_user().name }}</a>
        {% else %}
            <a href="/login">Sign in</a>
        {% endif %}

    Inside an ``EventStream`` generator (SSE), this returns the user captured at
    **connect time** — see :func:`get_user` for the pinned-identity semantics.
    """
    try:
        return _user_var.get()
    except LookupError:
        return _ANONYMOUS


class AuthMiddleware:
    """Dual-mode authentication middleware.

    Tries token auth first (stateless, for API clients), then falls
    back to session auth (stateful, for browsers). Sets the authenticated
    user in a ContextVar accessible via ``get_user()``.

    Middleware ordering::

        app.add_middleware(SessionMiddleware(...))  # 1st: sessions
        app.add_middleware(AuthMiddleware(...))      # 2nd: auth
        app.add_middleware(CSRFMiddleware())         # 3rd: CSRF

    Usage::

        from chirp.middleware.auth import AuthConfig, AuthMiddleware

        app.add_middleware(AuthMiddleware(AuthConfig(
            load_user=db.get_user_by_id,
            verify_token=db.get_user_by_token,
        )))
    """

    __slots__ = ("_config",)

    # Template globals auto-registered by App._freeze() when this
    # middleware is present. Any middleware can define this attribute.
    template_globals: ClassVar[dict[str, Any]] = {
        "current_user": current_user,
    }

    def __init__(self, config: AuthConfig | None = None) -> None:
        self._config = config or AuthConfig()

        if self._config.load_user is None and self._config.verify_token is None:
            msg = (
                "AuthConfig requires at least one of 'load_user' (session auth) "
                "or 'verify_token' (token auth) to be set."
            )
            raise ConfigurationError(msg)

    def _extract_token(self, request: Request) -> str | None:
        """Extract bearer token from the Authorization header."""
        header = request.headers.get(self._config.token_header.lower())
        if header is None:
            return None

        scheme = self._config.token_scheme
        prefix = f"{scheme} "
        if not header.startswith(prefix):
            return None

        token = header[len(prefix) :].strip()
        return token if token else None

    async def _authenticate_token(self, token: str | None) -> tuple[User | None, bool]:
        """Try token-based authentication.

        On success, the optional :class:`TokenRevocationStore` is consulted
        (token branch only, **after** ``verify_token`` returns a user). A
        revoked token emits ``auth.token.revoked``. Store errors **fail open**
        (token treated as not revoked) and emit
        ``auth.token.revocation_check_error``.

        Returns ``(user, revoked)``: ``user`` is the resolved :class:`User` or
        ``None`` (verify_token failed / no token / revoked); ``revoked`` is
        ``True`` only when ``verify_token`` succeeded but the store rejected the
        token — the caller uses it to suppress the ``auth.token.invalid`` event.
        """
        if self._config.verify_token is None:
            return None, False

        if token is None:
            return None, False

        user = await self._config.verify_token(token)
        if user is None:
            return None, False

        store = self._config.token_revocation_store
        if store is not None and await self._is_token_revoked(store, token, user):
            return None, True

        return user, False

    async def _resolve_claims(self, token: str) -> Mapping[str, Any]:
        """Resolve token claims via ``token_claims`` (sync or async).

        Mirrors the sync-or-async resolution in ``chirp.health.readiness``.
        """
        claims_fn = self._config.token_claims
        if claims_fn is None:
            return {}
        result = claims_fn(token)
        if isawaitable(result):
            # ``isawaitable`` narrows ``result`` to a bare ``Awaitable`` (the
            # generic param is erased at runtime), so the awaited value is typed
            # ``object``; the field declares ``Awaitable[Mapping[str, Any]]``.
            return cast("Mapping[str, Any]", await result)
        return result

    async def _is_token_revoked(self, store: TokenRevocationStore, token: str, user: User) -> bool:
        """Consult the revocation store. Fail OPEN on any store/claims error."""
        try:
            claims = await self._resolve_claims(token)
            jti = claims.get("jti")
            if jti is not None and await store.is_token_revoked(str(jti)):
                emit_security_event(
                    "auth.token.revoked",
                    user_id=user.id,
                    details={"reason": "jti", "jti": str(jti)},
                )
                return True

            iat = claims.get("iat")
            if iat is not None:
                cutoff = await store.user_revoked_at(user.id)
                if cutoff is not None and iat <= cutoff:
                    emit_security_event(
                        "auth.token.revoked",
                        user_id=user.id,
                        details={"reason": "user_cutoff", "iat": iat, "revoked_at": cutoff},
                    )
                    return True
        except Exception as exc:
            # Fail OPEN: availability over strict revocation. A revocation
            # backend blip must not 401 every API client. WARNING (not
            # exception) — this is expected degradation, not an app error.
            _log.warning("token revocation check failed (fail-open): %s", exc)
            emit_security_event(
                "auth.token.revocation_check_error",
                user_id=user.id,
                details={"error": type(exc).__name__},
            )
            return False
        return False

    async def _authenticate_session(self) -> User | None:
        """Try session-based authentication."""
        if self._config.load_user is None:
            return None

        from chirp.middleware.sessions import get_session

        try:
            session = get_session()
        except LookupError:
            msg = (
                "AuthMiddleware session auth requires SessionMiddleware. "
                "Add SessionMiddleware before AuthMiddleware, or use "
                "token auth only (set load_user=None)."
            )
            raise ConfigurationError(msg) from None

        user_id = session.get(self._config.session_key)
        if not user_id:
            return None

        user = await self._config.load_user(str(user_id))
        if user is None:
            return None

        version_fn = self._config.session_version
        if version_fn is not None:
            expected = version_fn(user)
            if expected is not None:
                stored = session.get(self._config.session_version_key)
                if str(expected) != str(stored):
                    emit_security_event(
                        "auth.session.version_mismatch",
                        user_id=user.id,
                        details={"stored": str(stored), "expected": str(expected)},
                    )
                    return None
        return user

    async def __call__(self, request: Request, next: Next) -> AnyResponse:
        """Authenticate the request, then dispatch."""
        cfg = self._config

        # Skip excluded paths
        if request.path in cfg.exclude_paths:
            token = _user_var.set(_ANONYMOUS)
            config_token = _active_config.set(cfg)
            try:
                return await next(request)
            finally:
                _user_var.reset(token)
                _active_config.reset(config_token)

        # Try token auth first (stateless, for API clients)
        raw_token = self._extract_token(request)
        user, revoked = await self._authenticate_token(raw_token)
        # A revoked token already emitted auth.token.revoked — do not also flag
        # it as auth.token.invalid. Both revoked and invalid fall back to session.
        if raw_token is not None and user is None and not revoked:
            emit_security_event(
                "auth.token.invalid",
                request=request,
                details={"scheme": cfg.token_scheme},
            )

        # Fall back to session auth (stateful, for browsers)
        if user is None:
            user = await self._authenticate_session()

        # Set ContextVars
        resolved_user: User = user if user is not None else _ANONYMOUS
        token = _user_var.set(resolved_user)
        config_token = _active_config.set(cfg)

        try:
            return await next(request)
        finally:
            _user_var.reset(token)
            _active_config.reset(config_token)
