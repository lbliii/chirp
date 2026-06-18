"""One-call secure-by-default middleware stack helper.

``secure_stack`` returns the secure-by-default middleware list in the
contract-passing order — ``SessionMiddleware`` -> ``CSRFMiddleware`` ->
``SecurityHeadersMiddleware`` — so an app author can wire the whole stack in one
line **without** anything being force-injected:

    from chirp.middleware.stack import secure_stack

    for mw in secure_stack(app.config):
        app.add_middleware(mw)

This is deliberately explicit-over-magic: it is a pure list-returning function
(the most inspectable/testable shape), not an auto-injecting hook. The app
author still calls ``add_middleware`` for each piece, and can drop or reorder
the list, swap in custom configs, or skip the helper entirely.

The generated stack passes the ``security_stack`` and ``csrf_session``
order contracts (same classes, same order) and inherits the Wave 2
``SessionConfig.secure="auto"`` posture: the session cookie's ``Secure`` flag is
resolved at freeze from ``config.env`` (``True`` for staging/production), **not**
from ``config.debug``. Coupling cookie security to ``debug`` is the footgun the
env-aware design exists to avoid, so this helper never reads ``debug``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from chirp.middleware.csrf import CSRFConfig, CSRFMiddleware
from chirp.middleware.security_headers import SecurityHeadersConfig, SecurityHeadersMiddleware
from chirp.middleware.sessions import (
    RedisSessionStore,
    SessionConfig,
    SessionMiddleware,
)

if TYPE_CHECKING:
    from chirp.config import AppConfig


def secure_stack(
    config: AppConfig,
    *,
    session: SessionConfig | None = None,
    csrf: CSRFConfig | None = None,
    headers: SecurityHeadersConfig | None = None,
    redis_url: str | None = None,
) -> list[Any]:
    """Return the secure-by-default middleware stack, in contract-passing order.

    The returned list is ``[SessionMiddleware, CSRFMiddleware,
    SecurityHeadersMiddleware]`` — exactly the order the ``security_stack`` and
    ``csrf_session`` contracts require (Session before CSRF, since the CSRF token
    lives in the session). Nothing is force-injected: the caller adds each
    middleware itself, typically::

        for mw in secure_stack(app.config):
            app.add_middleware(mw)

    Defaults are derived from *config*:

    - The session ``secret_key`` is read from ``config.secret_key``.
    - The session cookie's ``Secure`` flag is left as ``SessionConfig``'s
      ``secure="auto"`` default. Wave 2 freeze-resolution turns ``"auto"`` into
      ``True`` for ``env in ("staging", "production")`` and ``False`` otherwise
      (notably local development), keyed on ``config.env`` — never
      ``config.debug``. So a default-config app ships ``Secure`` session cookies
      in production without the author touching the field, while local dev keeps
      them non-Secure to avoid logging dev users out over HTTP.

    Pass ``session``/``csrf``/``headers`` to override any leg with your own
    fully-built config; when omitted, sane defaults are constructed. Pass
    ``redis_url`` to back sessions with ``RedisSessionStore`` (requires the
    ``redis`` extra) instead of the default signed-cookie store; it is ignored
    when an explicit ``session`` config is supplied (that config already owns its
    store choice).

    Args:
        config: The app config. Supplies ``secret_key`` and (via freeze
            resolution) the ``env``-derived cookie ``Secure`` posture.
        session: Optional explicit ``SessionConfig``. Overrides the derived
            default entirely (including ``redis_url``).
        csrf: Optional explicit ``CSRFConfig``. Defaults to ``CSRFConfig()``.
        headers: Optional explicit ``SecurityHeadersConfig``. Defaults to
            ``SecurityHeadersConfig()``.
        redis_url: Optional Redis URL. When set (and ``session`` is omitted),
            sessions are stored in ``RedisSessionStore`` rather than a signed
            cookie.

    Returns:
        ``[SessionMiddleware(...), CSRFMiddleware(...),
        SecurityHeadersMiddleware(...)]`` in that order.
    """
    if session is None:
        # secure is deliberately left at SessionConfig's "auto" default so the
        # Wave 2 freeze-resolution (resolve_cookie_secure) derives Secure from
        # config.env — not config.debug. This is cleaner than computing a bool
        # here: it keeps the single source of truth for cookie-Secure posture in
        # the session layer and means a default-config app passes cookie_secure
        # under --deploy (which re-resolves the configured "auto").
        if redis_url is not None:
            session = SessionConfig(
                secret_key=config.secret_key,
                store=RedisSessionStore(
                    SessionConfig(secret_key=config.secret_key),
                    redis_url,
                ),
            )
        else:
            session = SessionConfig(secret_key=config.secret_key)

    return [
        SessionMiddleware(session),
        CSRFMiddleware(csrf or CSRFConfig()),
        SecurityHeadersMiddleware(headers or SecurityHeadersConfig()),
    ]
