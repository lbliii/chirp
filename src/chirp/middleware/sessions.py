"""Session middleware — signed cookie sessions.

Session data is serialized as JSON and signed using ``itsdangerous``.
The session object is stored in a ContextVar, accessible via
``get_session()`` from any handler or middleware.

``itsdangerous`` is an optional dependency. If not installed,
``SessionMiddleware.__init__`` raises ``ConfigurationError``.
"""

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from chirp.errors import ConfigurationError
from chirp.http.request import Request
from chirp.http.response import Response
from chirp.middleware.protocol import Next

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


# -- Configuration --


@dataclass(frozen=True, slots=True)
class SessionConfig:
    """Session middleware configuration.

    ``secret_key`` is required — sessions are signed, not encrypted.
    """

    secret_key: str
    cookie_name: str = "chirp_session"
    max_age: int = 86400  # 24 hours
    path: str = "/"
    domain: str | None = None
    secure: bool = False
    httponly: bool = True
    samesite: str = "lax"


# -- Middleware --


class SessionMiddleware:
    """Signed cookie session middleware.

    Reads the session cookie, deserializes and verifies the signature,
    makes the session dict available via ``get_session()``, then
    serializes any changes back to a Set-Cookie header on the response.

    Usage::

        from chirp.middleware.sessions import SessionConfig, SessionMiddleware

        app.add_middleware(SessionMiddleware(SessionConfig(
            secret_key="my-secret-key",
        )))

        # In a handler:
        from chirp.middleware.sessions import get_session

        @app.route("/dashboard")
        def dashboard():
            session = get_session()
            session["visits"] = session.get("visits", 0) + 1
            return f"Visits: {session['visits']}"
    """

    __slots__ = ("_config", "_serializer")

    def __init__(self, config: SessionConfig) -> None:
        try:
            from itsdangerous import URLSafeTimedSerializer
        except ImportError:
            msg = (
                "SessionMiddleware requires the 'itsdangerous' package. "
                "Install it with: pip install itsdangerous"
            )
            raise ConfigurationError(msg) from None

        if not config.secret_key:
            msg = "SessionConfig.secret_key must not be empty."
            raise ConfigurationError(msg)

        self._config = config
        self._serializer = URLSafeTimedSerializer(config.secret_key)

    def _load_session(self, request: Request) -> dict[str, Any]:
        """Deserialize and verify the session cookie."""
        cookie_value = request.cookies.get(self._config.cookie_name)
        if not cookie_value:
            return {}

        try:
            data = self._serializer.loads(cookie_value, max_age=self._config.max_age)
        except Exception:
            return {}

        if not isinstance(data, dict):
            return {}
        return data

    def _save_session(self, response: Response, session: dict[str, Any]) -> Response:
        """Serialize the session dict and set the cookie on the response."""
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

    async def __call__(self, request: Request, next: Next) -> Response:
        """Load session, dispatch, then save session to response."""
        session = self._load_session(request)
        token = _session_var.set(session)

        try:
            response = await next(request)
        finally:
            _session_var.reset(token)

        # Always write the session cookie (even if unchanged —
        # refresh the signature timestamp for sliding expiration)
        return self._save_session(response, session)
