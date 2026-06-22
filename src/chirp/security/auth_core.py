"""Shared authenticate-or-deny core for declarative and imperative auth.

This module is the **single source of gate logic** used by both:

- the imperative decorators ``@login_required`` / ``@requires``
  (:mod:`chirp.security.decorators`); and
- the declarative ``RouteMeta.auth`` gate
  (:func:`chirp.pages.auth_gate.enforce_route_meta_auth`).

Before this module the two paths diverged: ``@requires`` emitted richer audit
payloads (``details={"missing": sorted(missing)}``) plus a ``_log.warning``,
while the declarative gate emitted a different payload shape and no log. That
divergence was the security risk — downstream SIEM keyed off one shape but not
the other. The core converges both on ONE canonical payload (documented in
``src/chirp/security/AGENTS.md``).

Design constraints:

- ``RouteMeta`` is static serializable data, so an :class:`AuthSpec` carries a
  policy **name** (``str``), never a callable. The core therefore takes an
  injected ``policy_resolver`` (``name -> callable | None``) so it stays
  registry-agnostic; the policy registry itself is wired in a later phase.
- Every existing ``str`` ``RouteMeta.auth`` value keeps identical runtime
  meaning via :func:`normalize_auth_spec`.
"""

from __future__ import annotations

import logging
import secrets
from collections.abc import Awaitable, Callable
from inspect import isawaitable
from typing import TYPE_CHECKING, Any

from chirp.errors import HTTPError
from chirp.pages.types import AuthSpec
from chirp.security.audit import emit_security_event

if TYPE_CHECKING:
    from chirp.http.request import Request

_log = logging.getLogger("chirp.security")

# Open string tokens: declare no gate. Mirrors enforce_route_meta_auth's
# historical behavior exactly. ``None`` and the empty/falsy case are also open.
_OPEN_TOKENS = frozenset({"none", "optional"})

# A policy resolver maps a policy NAME to a policy callable (or None if the name
# is unregistered). The callable signature matches @requires' policy hook:
# (user, request) -> bool | Awaitable[bool].
type PolicyCallable = Callable[[Any, Any], bool | Awaitable[bool]]
type PolicyResolver = Callable[[str], PolicyCallable | None]


def normalize_auth_spec(auth: str | AuthSpec | None) -> AuthSpec | None:
    """Parse ``str | AuthSpec | None`` into a canonical ``AuthSpec`` or ``None``.

    EXACT back-compat with the historical ``enforce_route_meta_auth`` string
    semantics — this preserves the runtime meaning of every existing value:

    - ``None`` / ``""`` / ``"none"`` / ``"optional"`` -> ``None`` (open, no gate)
    - ``"required"`` -> ``AuthSpec()`` (authn-only, no permissions/policy)
    - any other non-empty string ``s`` ->
      ``AuthSpec(permissions=(s,))`` (single required permission)
    - an existing ``AuthSpec`` passes through unchanged.

    An ``AuthSpec`` always requires authentication, so the open case is the only
    one that returns ``None``; there is no ``required`` flag to set.
    """
    if auth is None:
        return None
    if isinstance(auth, AuthSpec):
        return auth
    # Plain string: replicate the historical, case-sensitive token handling.
    if not auth or auth in _OPEN_TOKENS:
        return None
    if auth == "required":
        return AuthSpec()
    return AuthSpec(permissions=(auth,))


def _is_api_request(request: Any) -> bool:
    """Detect whether the request is from an API client (not a browser).

    Heuristic:
    - Has ``Authorization`` header -> API client
    - ``Accept`` prefers JSON over HTML -> API client
    - Otherwise -> browser
    """
    if request.headers.get("authorization"):
        return True

    accept = request.headers.get("accept", "")
    has_json = "application/json" in accept
    has_html = "text/html" in accept
    return bool(has_json and not has_html)


def _build_login_redirect(login_url: str, request_url: str) -> str:
    """Build a login redirect URL with a ``next`` parameter."""
    from urllib.parse import quote

    next_url = quote(request_url, safe="")
    separator = "&" if "?" in login_url else "?"
    return f"{login_url}{separator}next={next_url}"


def _next_url_for_request(request: Any) -> str:
    scoped_url = getattr(request, "scoped_url", None)
    if callable(scoped_url):
        return scoped_url(request.url)
    return request.url


def _deny_unauthenticated(request: Any) -> HTTPError:
    """Build the content-negotiated unauthenticated response.

    Browser -> 302 redirect to the login URL (with ``next``); API -> 401.
    Emits ``auth.require.unauthenticated`` for the API/no-login-url branches,
    matching historical behavior on both paths (the redirect branch does not
    emit — preserved verbatim).
    """
    from chirp.middleware.auth import _active_config

    if _is_api_request(request):
        emit_security_event("auth.require.unauthenticated", request=request)
        return HTTPError(status=401, detail="Authentication required")

    config = _active_config.get()
    login_url = config.login_url if config else "/login"
    if login_url:
        redirect_url = _build_login_redirect(login_url, _next_url_for_request(request))
        return HTTPError(
            status=302,
            detail="Login required",
            headers=(("Location", redirect_url),),
        )
    emit_security_event("auth.require.unauthenticated", request=request)
    return HTTPError(status=401, detail="Authentication required")


def _scope_held(required: str, held: frozenset[str]) -> bool:
    """Return whether ``required`` is in ``held``, comparing in constant time.

    A plain ``required in held`` set membership leaks (via early-exit string
    compare) how many leading characters of a scope matched. Webhook/cron scope
    tokens can be secret-bearing, so the issue's success criterion is a
    constant-time compare — route every scope-name equality through
    :func:`secrets.compare_digest` (the same primitive ``csrf.py`` /
    ``passwords.py`` use), never ``==``. The iteration count still varies with
    ``len(held)``, but each individual scope comparison is constant-time.
    """
    return any(secrets.compare_digest(required, candidate) for candidate in held)


async def enforce_auth(
    spec: AuthSpec,
    request: Request,
    user: Any,
    *,
    policy_resolver: PolicyResolver | None = None,
) -> None:
    """Authenticate-or-deny the resolved ``user`` against ``spec``.

    This is the single shared gate. It performs, in order:

    1. **Authentication** — if ``user`` is not authenticated, raise the
       content-negotiated response (302 -> login for browsers, 401 for APIs).
    2. **Permission check** — when ``spec.permissions`` is non-empty, the user
       must implement the permissions protocol (else 403) and satisfy the set:
       ``mode="all"`` requires every permission (subset);
       ``mode="any"`` requires a non-empty intersection.
    3. **Policy** — when ``spec.policy`` is set, resolve it via
       ``policy_resolver`` and call ``policy(user, request)``; deny (403) only
       on a falsy result from the RESOLVED callable (a real denial).
    4. **Scope check (machine auth)** — when ``spec.scopes`` is non-empty, the
       resolved client must implement the scopes protocol
       (:class:`~chirp.middleware.auth.ClientWithScopes`, else 403) and satisfy
       the scope set under ``spec.mode``. This is the machine-token axis,
       **independent of permissions**: a token-resolved client with the scope
       but no permissions passes, while a human user with permissions but not
       the scope fails. Scope-equality uses :func:`secrets.compare_digest`
       (constant-time). Scope enforcement is implicitly off — a spec with no
       ``scopes`` runs no scope step, so existing ``verify_token`` users are
       never newly denied (no separate enable flag). Denial emits
       ``authz.scope.denied`` with ``details={"missing": sorted([...])}``.

    An unresolved policy NAME (no ``policy_resolver`` wired, or the resolver
    returns ``None``) is a MISCONFIGURATION, not an auth denial: it raises
    ``LookupError`` -> a 500 at request time, consistent with the page wrapper's
    ``_resolve_policy`` (``app/registry.py``). It is NOT a 403 and emits NO
    ``authz.policy.denied`` event. This 500 is only a runtime backstop — the
    real guard is the ``auth_spec`` startup contract check, which ERRORs on any
    referenced ``AuthSpec.policy`` that is not registered.

    Audit events use the ONE canonical payload (see ``AGENTS.md``); the
    permission/policy warnings are logged via ``chirp.security``.

    Args:
        spec: The resolved, non-open ``AuthSpec`` to enforce.
        request: The active request (for content negotiation + audit context).
        user: The resolved current user (``get_user()`` result).
        policy_resolver: ``name -> callable | None`` for named policies. Only
            consulted when ``spec.policy`` is set. An unresolved name (no
            resolver, or the resolver returns ``None``) fails loud
            (``LookupError`` -> 500), never a silent 403.
    """
    # 1. Authentication.
    if not getattr(user, "is_authenticated", False):
        raise _deny_unauthenticated(request)

    # 2. Permissions.
    if spec.permissions:
        from chirp.middleware.auth import UserWithPermissions

        if not isinstance(user, UserWithPermissions):
            _log.warning(
                "User %s model does not implement permissions protocol",
                user.id,
            )
            emit_security_event(
                "authz.permission.denied",
                request=request,
                user_id=user.id,
                details={
                    "reason": "missing_permissions_protocol",
                    "missing": sorted(spec.permissions),
                },
            )
            raise HTTPError(status=403, detail="Forbidden")

        required = frozenset(spec.permissions)
        held = user.permissions
        if spec.mode == "any":
            satisfied = bool(required & held)
            missing = sorted(required) if not satisfied else []
        else:  # "all"
            satisfied = required.issubset(held)
            missing = sorted(required - held)
        if not satisfied:
            _log.warning(
                "User %s missing permissions (mode=%s): %s",
                user.id,
                spec.mode,
                ", ".join(missing),
            )
            emit_security_event(
                "authz.permission.denied",
                request=request,
                user_id=user.id,
                details={"missing": missing},
            )
            raise HTTPError(status=403, detail="Forbidden")

    # 3. Named policy.
    if spec.policy is not None:
        policy = policy_resolver(spec.policy) if policy_resolver is not None else None
        if policy is None:
            # An unresolved policy NAME is a MISCONFIGURATION, not a denial: fail
            # loud (500), never a silent 403, and emit no authz.policy.denied
            # event. Mirrors app/registry.py _resolve_policy raising LookupError;
            # the auth_spec startup check is the real guard.
            msg = (
                f"AuthSpec.policy {spec.policy!r} could not be resolved "
                f"({'resolver returned None' if policy_resolver is not None else 'no policy resolver wired'}). "
                "Register it with app.register_policy(name, fn) during setup."
            )
            raise LookupError(msg)

        allowed = policy(user, request)
        if isawaitable(allowed):
            allowed = await allowed
        if not allowed:
            emit_security_event(
                "authz.policy.denied",
                request=request,
                user_id=user.id,
                details={"policy": spec.policy},
            )
            raise HTTPError(status=403, detail="Forbidden")

    # 4. Scopes (machine-auth axis). Implicitly off when spec.scopes is empty.
    if spec.scopes:
        from chirp.middleware.auth import ClientWithScopes

        if not isinstance(user, ClientWithScopes):
            _log.warning(
                "Client %s model does not implement scopes protocol",
                user.id,
            )
            emit_security_event(
                "authz.scope.denied",
                request=request,
                user_id=user.id,
                details={
                    "reason": "missing_scopes_protocol",
                    "missing": sorted(spec.scopes),
                },
            )
            raise HTTPError(status=403, detail="Forbidden")

        required = spec.scopes
        held = user.scopes
        if spec.mode == "any":
            satisfied = any(_scope_held(scope, held) for scope in required)
            missing = sorted(set(required)) if not satisfied else []
        else:  # "all"
            missing = sorted({scope for scope in required if not _scope_held(scope, held)})
            satisfied = not missing
        if not satisfied:
            _log.warning(
                "Client %s missing scopes (mode=%s): %s",
                user.id,
                spec.mode,
                ", ".join(missing),
            )
            emit_security_event(
                "authz.scope.denied",
                request=request,
                user_id=user.id,
                details={"missing": missing},
            )
            raise HTTPError(status=403, detail="Forbidden")
