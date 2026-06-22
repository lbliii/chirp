"""Secure stack + session signal middleware. DESIGN.md §7."""

import notifications
import session_store
import users
from wallet import balance as meow_balance

from chirp.middleware.auth import AuthConfig, AuthMiddleware, current_user
from chirp.middleware.csrf import CSRFConfig, CSRFMiddleware
from chirp.middleware.security_headers import SecurityHeadersConfig, SecurityHeadersMiddleware
from chirp.middleware.sessions import SessionConfig, SessionMiddleware

from wiring.app_factory import _signal_audience_key, app, config


async def load_user(user_id: str) -> users.User | None:
    """AuthConfig.load_user — resolve the session's user id back to a User."""
    return users.get(user_id)


class _EnsureStoreKeyMiddleware:
    """Assign a per-browser ``__store_key`` on every session for isolated demo state."""

    async def __call__(self, request, next):
        session_store.ensure_store_key()
        return await next(request)


class _SessionSignalsMiddleware:
    """Seed session-scoped signal SSR + bind the SSE audience for this visitor."""

    async def __call__(self, request, next):
        from chirp.realtime.signal_globals import reset_signal_audience, set_signal_audience

        session_store.ensure_store_key()
        key = session_store.session_key()
        aud = _signal_audience_key()
        token = set_signal_audience(aud)
        registry = app._mutable_state.signal_registry
        try:
            if registry is not None and aud and current_user().is_authenticated:
                with session_store.bind(key):
                    registry.seed("balance", meow_balance(), audience_key=aud)
                    registry.seed("notifications", notifications.snapshot(), audience_key=aud)
            elif not current_user().is_authenticated:
                reset_signal_audience(token)
                token = set_signal_audience("")
            return await next(request)
        finally:
            reset_signal_audience(token)


def register(app_instance) -> None:
    """Wire Session → store key → Auth → signal seed → CSRF → security headers."""
    app_instance.add_middleware(
        SessionMiddleware(
            SessionConfig(
                secret_key=config.secret_key,
                cookie_name="chirp_session_lucky_cat",
                httponly=True,
                samesite="lax",
            )
        )
    )
    app_instance.add_middleware(_EnsureStoreKeyMiddleware())
    app_instance.add_middleware(AuthMiddleware(AuthConfig(load_user=load_user, login_url="/login")))
    app_instance.add_middleware(_SessionSignalsMiddleware())
    app_instance.add_middleware(CSRFMiddleware(CSRFConfig()))
    app_instance.add_middleware(
        SecurityHeadersMiddleware(SecurityHeadersConfig(content_security_policy=None))
    )
