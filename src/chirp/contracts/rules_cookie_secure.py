"""Cookie-hardening contract checks — Secure session cookies + HSTS nudge.

Two env-aware, deploy-escalating rules that guard the cookie-transport posture
the runtime now resolves at freeze (``resolve_cookie_secure`` /
``SessionMiddleware.secure``). Both mirror ``rules_security_stack`` /
``rules_safety``: middleware is detected by class **name** (never ``isinstance``,
never importing middleware into the contracts layer), severity is read from
``config.env`` so ``chirp check --deploy`` escalates via the production-posture
config view, and the check shares ONE source of truth with the runtime by
importing ``resolve_cookie_secure`` from ``chirp.middleware.sessions``.

Categories:

- ``cookie_secure``: a ``SessionMiddleware`` is present but the session cookie it
  emits is not ``Secure`` under production posture. Store-AGNOSTIC — both
  ``CookieSessionStore`` (data-in-cookie) and ``RedisSessionStore``
  (session-id-in-cookie) emit a ``Set-Cookie``, so a ``Secure``-less Redis
  session-id cookie is equally exploitable (sniffable over a plaintext path →
  session hijack). Severity is ERROR in production, WARNING in staging, silent in
  development. A second, **env-independent** ERROR fires when
  ``samesite=='none'`` with effective ``secure==False``: browsers silently DROP a
  ``SameSite=None`` cookie that is not ``Secure``, so the session breaks in every
  environment — a correctness footgun, not just a hardening gap.

- ``hsts``: in production, an app with an auth/mutating surface that leaves
  ``strict_transport_security`` unset gets a WARNING + docs nudge. HSTS is NOT
  auto-emitted and ``strict_transport_security=None`` is NOT overloaded to mean
  "auto" — ``None`` stays "off". An HSTS header is an irreversible multi-year
  browser pin; emitting it on a declared-env *guess* (the app may be reached over
  plain HTTP behind a misconfigured proxy) is worse than the gap. So this is a
  WARNING only — never promoted to ERROR, never an auto-injected header.
"""

from typing import TYPE_CHECKING, Any

from chirp.contracts.rules_security_stack import is_mutating_route
from chirp.contracts.types import ContractIssue, Severity

if TYPE_CHECKING:
    from chirp.routing.router import Router

# Detected by class NAME (see module docstring) — no middleware import.
_SESSION_MIDDLEWARE = "SessionMiddleware"
_SECURITY_HEADERS_MIDDLEWARE = "SecurityHeadersMiddleware"


def _effective_secure(mw: Any, env: str) -> bool:
    """Resolve the effective ``Secure`` flag of a SessionMiddleware's cookie.

    Read the **originally-configured** value via the ``configured_secure``
    accessor — the unresolved ``"auto"`` | bool — and re-resolve it through the
    shared :func:`resolve_cookie_secure` against the posture *env*. This is the
    crux of correct ``--deploy`` behavior: the compiler resolves ``"auto"`` to a
    concrete bool AT FREEZE using the real (often development) env, so reading
    the freeze-resolved ``secure`` would burn the ``"auto"`` sentinel and falsely
    ERROR a deploy-ready default app under production posture. Re-resolving the
    *configured* value against the posture env evaluates the app as it WOULD be
    in that env (``"auto"`` → Secure in production). Falls back to ``secure``
    then ``"auto"`` for a custom middleware without the accessor.

    ``resolve_cookie_secure`` is imported lazily: ``chirp.middleware.sessions``
    pulls in ``itsdangerous`` (the optional ``sessions`` extra) at module load,
    and the contracts layer must import cleanly without it. The import only runs
    when a ``SessionMiddleware`` is actually present, by which point the sessions
    machinery is necessarily installed.
    """
    from chirp.middleware.sessions import resolve_cookie_secure

    secure = getattr(mw, "configured_secure", None)
    if secure is None:
        secure = getattr(mw, "secure", None)
    return resolve_cookie_secure(secure if secure is not None else "auto", env=env)


def _session_samesite(mw: Any) -> str:
    """Read the effective ``samesite`` of the cookie this middleware emits.

    Reads the store's config when present (the store owns the cookie attributes),
    falling back to the middleware's own config. Defaults to ``"lax"`` (the
    ``SessionConfig`` default) when neither is readable.
    """
    store = getattr(mw, "_store", None)
    store_config = getattr(store, "_config", None)
    if store_config is not None:
        return str(getattr(store_config, "samesite", "lax")).lower()
    config = getattr(mw, "_config", None)
    if config is not None:
        return str(getattr(config, "samesite", "lax")).lower()
    return "lax"


def check_cookie_secure(
    config: Any,
    middleware_list: list[Any],
) -> list[ContractIssue]:
    """Flag a non-``Secure`` session cookie under production posture.

    No-op when no ``SessionMiddleware`` is registered — ``security_stack`` already
    owns the presence check. When a ``SessionMiddleware`` IS present and its
    effective ``Secure`` flag resolves ``False``:

    - ``samesite=='none'`` + ``secure==False`` → **ERROR, env-independent**.
      Browsers silently drop ``SameSite=None`` cookies that are not ``Secure``,
      so the session is broken in every environment. This is a correctness bug,
      reported regardless of ``env``.
    - otherwise → env-aware **hardening** gap: ERROR in production, WARNING in
      staging, silent in development (so dev apps and shipped examples — which run
      over plain HTTP and correctly resolve ``secure=False`` — stay clean).

    Store-agnostic: ``CookieSessionStore`` and ``RedisSessionStore`` both emit a
    ``Set-Cookie``, so a ``Secure``-less cookie is exploitable either way. The
    check reads :func:`SessionMiddleware.secure`, which already routes through the
    authoritative store config.
    """
    issues: list[ContractIssue] = []

    env = getattr(config, "env", "development")
    sessions = [mw for mw in middleware_list if type(mw).__name__ == _SESSION_MIDDLEWARE]
    if not sessions:
        return issues

    for mw in sessions:
        if _effective_secure(mw, env):
            continue  # Secure cookie — nothing to flag.

        samesite = _session_samesite(mw)
        if samesite == "none":
            # Env-INDEPENDENT: a SameSite=None cookie without Secure is silently
            # dropped by every browser — the session breaks in dev too.
            issues.append(
                ContractIssue(
                    severity=Severity.ERROR,
                    category="cookie_secure",
                    message=(
                        "SessionMiddleware sets samesite='none' but the session "
                        "cookie is not Secure. Browsers silently DROP a "
                        "SameSite=None cookie that is not Secure, so the session "
                        "will not persist in any environment. Set "
                        "SessionConfig(secure=True) (or keep secure='auto' and "
                        "run over HTTPS), or use samesite='lax'/'strict'."
                    ),
                )
            )
            continue

        # Env-aware hardening gap.
        if env in ("production", "staging"):
            severity = Severity.ERROR if env == "production" else Severity.WARNING
            issues.append(
                ContractIssue(
                    severity=severity,
                    category="cookie_secure",
                    message=(
                        "Session cookie is not Secure while env="
                        f"'{env}'. The session cookie (session data or session "
                        "id) can be sniffed over a plaintext path and replayed "
                        "to hijack the session. Keep SessionConfig(secure='auto') "
                        "(resolves to Secure in production/staging) or set "
                        "secure=True before deploying."
                    ),
                )
            )

    return issues


def _hsts_configured(config: Any, middleware_list: list[Any]) -> bool:
    """True when HSTS is effectively set, anywhere it can be configured.

    HSTS lives in two places: ``AppConfig.strict_transport_security`` (which the
    compiler auto-wires into a ``SecurityHeadersMiddleware`` in production-with-TLS)
    AND a ``SecurityHeadersConfig.strict_transport_security`` on a hand-added
    ``SecurityHeadersMiddleware``. Treat either as "set" so a user who configures
    HSTS only on their own middleware does not get a false WARNING.

    Also treat HSTS as configured when the compiler will auto-wire it: in
    production with ``ssl_certfile`` set (TLS terminated in-process), the
    compiler appends a ``SecurityHeadersMiddleware`` emitting HSTS at runtime
    even though ``strict_transport_security`` is unset here — so nudging would
    be a false positive for a correctly-configured TLS app.
    """
    if getattr(config, "strict_transport_security", None):
        return True
    if getattr(config, "env", None) == "production" and getattr(config, "ssl_certfile", None):
        return True
    for mw in middleware_list:
        if type(mw).__name__ != _SECURITY_HEADERS_MIDDLEWARE:
            continue
        mw_config = getattr(mw, "config", None)
        if getattr(mw_config, "strict_transport_security", None):
            return True
    return False


def check_hsts(
    router: Router,
    config: Any,
    middleware_list: list[Any],
    discovered_routes: list[Any] | None = None,
) -> list[ContractIssue]:
    """Nudge for missing HSTS on a production app with an auth/mutating surface.

    WARNING (never ERROR) when **all** hold:

    - ``env == 'production'`` (HSTS is meaningless in dev; a guess in staging is
      not nudged either — only the declared production posture),
    - ``strict_transport_security`` is unset everywhere it can be configured
      (``AppConfig`` field AND any ``SecurityHeadersMiddleware`` config), and
    - the app has an auth/mutating surface (reuses :func:`is_mutating_route` —
      the same predicate ``security_stack`` owns).

    Deliberately a WARNING + docs nudge ONLY. Chirp does NOT auto-emit an HSTS
    header from a declared-env guess and does NOT overload
    ``strict_transport_security=None`` to mean "auto": ``None`` stays "off". HSTS
    is an irreversible multi-year browser pin — emitting it because ``env`` *says*
    production (while the app may actually be reached over plain HTTP behind a
    misconfigured proxy) is worse than the gap.
    """
    issues: list[ContractIssue] = []

    env = getattr(config, "env", "development")
    if env != "production":
        return issues
    if _hsts_configured(config, middleware_list):
        return issues

    candidate_routes = list(getattr(router, "routes", []))
    if discovered_routes:
        candidate_routes.extend(discovered_routes)
    if not any(is_mutating_route(route) for route in candidate_routes):
        return issues

    issues.append(
        ContractIssue(
            severity=Severity.WARNING,
            category="hsts",
            message=(
                "env='production' with an auth/mutating surface but "
                "strict_transport_security is unset. Without HSTS a first request "
                "over plain HTTP can be downgraded/MITM'd before the redirect to "
                "HTTPS. Set AppConfig(strict_transport_security='max-age=63072000; "
                "includeSubDomains') (or a SecurityHeadersMiddleware with it) once "
                "you have confirmed the app is only ever reached over HTTPS — HSTS "
                "is an irreversible multi-year browser pin, so Chirp will not emit "
                "it from a declared-env guess."
            ),
        )
    )
    return issues
