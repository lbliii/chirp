"""Security-stack contract check — secure-by-default as a contract (#182).

This category is the canonical owner of the **mutating route** definition
referenced by the forms/auth epics. Other rules that need "what counts as a
mutating route" import ``MUTATING_METHODS`` / ``is_mutating_route`` from here.

A route is **mutating** when either is true:

1. It accepts a mutating HTTP method (POST/PUT/PATCH/DELETE), or
2. It is a filesystem page that ships ``_actions.py`` form actions
   (``route.actions`` is non-empty). This is Chirp's canonical form-action
   pattern: the ``page.py`` may declare only ``get()``, yet the page mutates
   state via POST-to-self dispatched on the ``_action`` form field. Such a page
   is method-GET in the router but is unmistakably a mutating surface, so it
   must clear the same CSRF/Session bar as a POST route.

Category:
- ``security_stack``: a mutating route exists but the security stack is not
  fully wired.

Severity matrix (env-aware, mirroring ``rules_safety``/``rules_deploy``):
- Missing ``CSRFMiddleware`` **or** ``SessionMiddleware`` on an app with any
  mutating route → ``ERROR`` in production, ``WARNING`` in staging, and
  **silent** in development (the default) so dev apps and shipped examples stay
  clean.
- Missing ``SecurityHeadersMiddleware`` → ``WARNING`` unconditionally (whenever
  any mutating route exists), independent of env. This is the agreed decision:
  CSRF/Session and SecurityHeaders are two distinct severity tracks.

No middleware is force-injected into ``App()``. The lever is this contract plus
scaffold defaults (#183), per the explicit-over-magic convention.

Middleware presence is detected by class **name** (``type(mw).__name__``), not
``isinstance``. This matches the established pattern in
``rules_safety.check_csrf_session_order`` and
``rules_csrf_forms._csrf_middleware_active``: it avoids importing middleware
classes into the contracts layer (keeping the dependency direction clean). The
trade-off is that a user subclass is only recognised when it keeps the same
class name.
"""

from typing import TYPE_CHECKING, Any

from chirp.contracts.types import ContractIssue, Severity

if TYPE_CHECKING:
    from chirp.routing.router import Router

# Canonical mutating-method set. ``security_stack`` is the named owner of this
# definition; other route-level rules (e.g. rules_nojs_floor) use the same set.
MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Middleware class names that make up the secure-by-default stack.
_CSRF_MIDDLEWARE = "CSRFMiddleware"
_SESSION_MIDDLEWARE = "SessionMiddleware"
_SECURITY_HEADERS_MIDDLEWARE = "SecurityHeadersMiddleware"


def is_mutating_route(route: Any) -> bool:
    """Return True when ``route`` is a mutating surface.

    Canonical predicate for the "mutating route" definition. A route is
    mutating when **either**:

    - it accepts a mutating HTTP method — ``route.methods`` intersects
      :data:`MUTATING_METHODS`; **or**
    - it is a filesystem page carrying ``_actions.py`` form actions —
      ``route.actions`` is non-empty. These pages mutate state via POST-to-self
      on the ``_action`` form field even when ``page.py`` declares only
      ``get()``, so they must be treated as mutating.

    Runtime ``Route`` objects expose ``methods`` only; discovered ``PageRoute``
    objects expose both ``methods`` and ``actions``. ``getattr`` defaults keep
    the predicate total for either shape.
    """
    methods = getattr(route, "methods", ()) or ()
    if MUTATING_METHODS & {str(m).upper() for m in methods}:
        return True
    return bool(getattr(route, "actions", ()) or ())


def _middleware_class_names(middleware_list: list[Any]) -> set[str]:
    return {type(mw).__name__ for mw in middleware_list}


def check_security_stack(
    router: Router,
    config: Any,
    middleware_list: list[Any],
    discovered_routes: list[Any] | None = None,
) -> list[ContractIssue]:
    """Flag mutating routes that are not protected by the security stack.

    A mutating route needs CSRF + session protection. A route is mutating when
    it accepts a mutating HTTP method (POST/PUT/PATCH/DELETE) **or** is a
    filesystem page carrying ``_actions.py`` form actions (POST-to-self on the
    ``_action`` field; see :func:`is_mutating_route`). When either
    ``CSRFMiddleware`` or ``SessionMiddleware`` is missing, this ERRORs in
    production and WARNs in staging (silent in development). Missing
    ``SecurityHeadersMiddleware`` always WARNs. No issue is emitted for an app
    with no mutating routes.

    ``discovered_routes`` carries the filesystem ``PageRoute`` objects (which
    expose ``actions``); runtime ``router.routes`` expose ``methods`` only. Both
    are scanned so a GET-only page backed by form actions is still flagged.

    Note: referenced (transport) routes are **included** — a mutating SSE/API
    endpoint still needs CSRF/session protection, unlike the no-JS floor which
    excludes them. This is intentional and flagged for steward sign-off.
    """
    issues: list[ContractIssue] = []

    candidate_routes = list(getattr(router, "routes", []))
    if discovered_routes:
        candidate_routes.extend(discovered_routes)
    has_mutating = any(is_mutating_route(route) for route in candidate_routes)
    if not has_mutating:
        return issues

    env = getattr(config, "env", "development")
    present = _middleware_class_names(middleware_list)

    missing_protection: list[str] = []
    if _CSRF_MIDDLEWARE not in present:
        missing_protection.append(_CSRF_MIDDLEWARE)
    if _SESSION_MIDDLEWARE not in present:
        missing_protection.append(_SESSION_MIDDLEWARE)

    # CSRF/Session: env-aware. Silent in development so dev apps and shipped
    # examples stay clean; ERROR in production, WARNING in staging.
    if missing_protection and env in ("production", "staging"):
        severity = Severity.ERROR if env == "production" else Severity.WARNING
        missing = " and ".join(missing_protection)
        issues.append(
            ContractIssue(
                severity=severity,
                category="security_stack",
                message=(
                    f"App has mutating route(s) (POST/PUT/PATCH/DELETE) but "
                    f"{missing} is not registered while env='{env}'. "
                    "Mutations are unprotected against CSRF/session forgery — "
                    "register SessionMiddleware then CSRFMiddleware (and "
                    "SecurityHeadersMiddleware) before deploying."
                ),
            )
        )

    # SecurityHeaders: WARNING-only, env-independent.
    if _SECURITY_HEADERS_MIDDLEWARE not in present:
        issues.append(
            ContractIssue(
                severity=Severity.WARNING,
                category="security_stack",
                message=(
                    "App has mutating route(s) but SecurityHeadersMiddleware is "
                    "not registered. Add SecurityHeadersMiddleware for "
                    "clickjacking/MIME-sniffing/referrer protections."
                ),
            )
        )

    return issues
