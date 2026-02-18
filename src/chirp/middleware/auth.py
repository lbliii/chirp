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

from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, ClassVar, Protocol, runtime_checkable

from chirp.errors import ConfigurationError
from chirp.http.request import Request
from chirp.middleware.protocol import AnyResponse, Next
from chirp.security.audit import emit_security_event

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


def get_user() -> User:
    """Return the current authenticated user (or ``AnonymousUser``).

    Raises ``LookupError`` if called outside a request with
    ``AuthMiddleware`` active.
    """
    try:
        return _user_var.get()
    except LookupError:
        msg = (
            "No auth context. Ensure AuthMiddleware is added "
            "to the app before accessing the user."
        )
        raise LookupError(msg) from None


# ---------------------------------------------------------------------------
# Login / Logout helpers
# ---------------------------------------------------------------------------

# Module-level reference to the active config, set by AuthMiddleware.__init__
_active_config: ContextVar[AuthConfig | None] = ContextVar(
    "chirp_auth_config", default=None
)


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
    """

    session_key: str = "user_id"
    token_header: str = "Authorization"
    token_scheme: str = "Bearer"
    load_user: Callable[[str], Awaitable[User | None]] | None = None
    verify_token: Callable[[str], Awaitable[User | None]] | None = None
    session_version: Callable[[User], str | int | None] | None = None
    session_version_key: str = "_session_version"
    login_url: str | None = "/login"
    exclude_paths: frozenset[str] = frozenset()


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

    async def _authenticate_token(self, token: str | None) -> User | None:
        """Try token-based authentication."""
        if self._config.verify_token is None:
            return None

        if token is None:
            return None

        return await self._config.verify_token(token)

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
        user = await self._authenticate_token(raw_token)
        if raw_token is not None and user is None:
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
