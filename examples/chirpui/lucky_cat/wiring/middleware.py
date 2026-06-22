"""Secure stack + session signal middleware. DESIGN.md §7."""

import notifications
import session_store
import users
from wallet import balance as meow_balance
from wiring.app_factory import _signal_audience_key, app, config

from chirp.middleware.auth import AuthConfig, AuthMiddleware
from chirp.middleware.csrf import CSRFConfig, CSRFMiddleware
from chirp.middleware.security_headers import SecurityHeadersConfig, SecurityHeadersMiddleware
from chirp.middleware.session_signals import SessionSignalConfig, SessionSignalMiddleware
from chirp.middleware.sessions import SessionConfig, SessionMiddleware


async def load_user(user_id: str) -> users.User | None:
    """AuthConfig.load_user — resolve the session's user id back to a User."""
    return users.get(user_id)


class _EnsureStoreKeyMiddleware:
    """Assign a per-browser ``__store_key`` on every session for isolated demo state."""

    async def __call__(self, request, next):
        session_store.ensure_store_key()
        return await next(request)


def _session_signal_seeds() -> dict[str, object]:
    return {
        "balance": meow_balance,
        "notifications": notifications.snapshot,
    }


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
    app_instance.add_middleware(
        SessionSignalMiddleware(
            SessionSignalConfig(
                app=app,
                audience_key=_signal_audience_key,
                seeds=_session_signal_seeds,
                seed_context=lambda: session_store.bind(session_store.session_key()),
            )
        )
    )
    app_instance.add_middleware(CSRFMiddleware(CSRFConfig()))
    app_instance.add_middleware(
        SecurityHeadersMiddleware(SecurityHeadersConfig(content_security_policy=None))
    )

    @app_instance.on_worker_startup
    async def _start_live_market_feed() -> None:
        from feed import start_live_feed

        await start_live_feed()

    @app_instance.on_worker_shutdown
    async def _shutdown_live_market_feed() -> None:
        from feed import shutdown_live_feed

        await shutdown_live_feed()
