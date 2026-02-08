"""CSRF protection middleware — token-based, session-backed.

Generates a random token per session, validates it on state-changing
requests (POST, PUT, PATCH, DELETE). Rejects with 403 if the token
is missing or invalid.

Requires ``SessionMiddleware`` — the CSRF token is stored in the session.

Usage::

    from chirp.middleware.csrf import CSRFConfig, CSRFMiddleware
    from chirp.middleware.sessions import SessionConfig, SessionMiddleware

    app.add_middleware(SessionMiddleware(SessionConfig(secret_key="...")))
    app.add_middleware(CSRFMiddleware(CSRFConfig()))

Templates::

    <form method="post">
        {{ csrf_field() }}
        ...
    </form>

htmx (via meta tag)::

    <meta name="csrf-token" content="{{ csrf_token() }}">
"""

import secrets
from contextvars import ContextVar
from dataclasses import dataclass

from chirp.errors import ConfigurationError, HTTPError
from chirp.http.request import Request
from chirp.middleware.protocol import AnyResponse, Next

# -- CSRF token ContextVar (accessible from template globals) --

_csrf_token_var: ContextVar[str | None] = ContextVar("chirp_csrf_token", default=None)

# Methods that mutate state and need CSRF protection
_UNSAFE_METHODS: frozenset[str] = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def get_csrf_token() -> str:
    """Return the current CSRF token.

    Raises ``LookupError`` if called outside a request with
    ``CSRFMiddleware`` active.
    """
    token = _csrf_token_var.get()
    if token is None:
        msg = (
            "No CSRF token available. Ensure CSRFMiddleware is added "
            "to the app after SessionMiddleware."
        )
        raise LookupError(msg)
    return token


def csrf_field() -> str:
    """Render a hidden input field with the CSRF token.

    For use as a template global::

        <form method="post">
            {{ csrf_field() }}
            ...
        </form>

    Renders: ``<input type="hidden" name="_csrf_token" value="...">``
    """
    from kida.utils.html import Markup

    token = get_csrf_token()
    return Markup(f'<input type="hidden" name="_csrf_token" value="{token}">')


def csrf_token() -> str:
    """Return the raw CSRF token string.

    For use as a template global in meta tags::

        <meta name="csrf-token" content="{{ csrf_token() }}">
    """
    return get_csrf_token()


# -- Configuration --


@dataclass(frozen=True, slots=True)
class CSRFConfig:
    """CSRF middleware configuration.

    Attributes:
        field_name: Form field name for the token.
        header_name: HTTP header name for AJAX/htmx requests.
        session_key: Key used to store the token in the session.
        token_length: Length of the random token in bytes (hex-encoded).
        exempt_paths: Paths that skip CSRF validation (e.g. API webhooks).
    """

    field_name: str = "_csrf_token"
    header_name: str = "X-CSRF-Token"
    session_key: str = "_csrf_token"
    token_length: int = 32
    exempt_paths: frozenset[str] = frozenset()


# -- Middleware --


class CSRFMiddleware:
    """Token-based CSRF protection middleware.

    On every request:
    1. Loads or generates a CSRF token in the session.
    2. Makes the token available via ``get_csrf_token()`` and template globals.
    3. On unsafe methods (POST, PUT, PATCH, DELETE), validates the token
       from either the form body or the request header.
    4. Rejects with 403 if the token is missing or invalid.

    Requires ``SessionMiddleware`` to be registered first.
    """

    __slots__ = ("_config",)

    def __init__(self, config: CSRFConfig | None = None) -> None:
        self._config = config or CSRFConfig()

    async def __call__(self, request: Request, next: Next) -> AnyResponse:
        """Validate CSRF token on unsafe methods, then dispatch."""
        from chirp.middleware.sessions import get_session

        # Load session (requires SessionMiddleware to be active)
        try:
            session = get_session()
        except LookupError:
            msg = (
                "CSRFMiddleware requires SessionMiddleware. "
                "Add SessionMiddleware before CSRFMiddleware."
            )
            raise ConfigurationError(msg) from None

        # Get or generate CSRF token
        cfg = self._config
        token = session.get(cfg.session_key)
        if not token:
            token = secrets.token_hex(cfg.token_length)
            session[cfg.session_key] = token

        # Make token available via ContextVar
        cv_token = _csrf_token_var.set(token)

        try:
            # Validate on unsafe methods
            if request.method in _UNSAFE_METHODS and request.path not in cfg.exempt_paths:
                await _validate_token(request, token, cfg)

            return await next(request)
        finally:
            _csrf_token_var.reset(cv_token)


async def _validate_token(request: Request, expected: str, config: CSRFConfig) -> None:
    """Check the CSRF token from form data or header.

    Raises ``HTTPError(403)`` if the token is missing or invalid.
    """
    # Check header first (htmx, AJAX)
    submitted = request.headers.get(config.header_name)

    # Fall back to form body
    if submitted is None:
        ct = request.content_type or ""
        if "form" in ct:
            form = await request.form()
            submitted = form.get(config.field_name)

    if submitted is None:
        raise HTTPError(status=403, detail="CSRF token missing")

    if not secrets.compare_digest(submitted, expected):
        raise HTTPError(status=403, detail="CSRF token invalid")
