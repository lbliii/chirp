"""Declarative auth enforcement from filesystem route metadata.

This is the DECLARATIVE auth gate (awaited per mounted page in
``app/registry.py``). It now delegates to the SAME shared core as the
imperative ``@login_required`` / ``@requires`` decorators
(:func:`chirp.security.auth_core.enforce_auth`), so both paths produce
identical 302/401/403 outcomes and identical ``emit_security_event`` payloads.
``pages`` may depend on ``security`` (security primitives sit below pages).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from chirp.http.request import Request
from chirp.pages.types import RouteMeta
from chirp.security.auth_core import enforce_auth, normalize_auth_spec

if TYPE_CHECKING:
    from chirp.security.auth_core import PolicyResolver


async def enforce_route_meta_auth(
    meta: RouteMeta | None,
    request: Request,
    *,
    policy_resolver: PolicyResolver | None = None,
) -> None:
    """Enforce ``RouteMeta.auth`` before a mounted page handler runs.

    ``auth`` accepts a plain string (back-compatible) or a structured
    :class:`chirp.pages.types.AuthSpec`. String semantics (preserved exactly):

    - ``None``, ``""``, ``"none"``, ``"optional"`` — no gate
    - ``"required"`` — authenticated user required (browser redirect or 401)
    - any other string — treated as a single required permission via
      ``UserWithPermissions.permissions``

    An :class:`AuthSpec` additionally supports permission sets with
    ``mode="all"`` / ``mode="any"`` and a named policy. Normalization and
    enforcement are shared with the decorator path.

    ``policy_resolver`` maps an ``AuthSpec.policy`` NAME to the registered
    callable (``app.register_policy``); the page wrapper wires it from the app's
    policy registry. When a spec names a policy that the resolver cannot resolve
    (unregistered name, or no resolver wired), the shared core fails LOUD
    (``LookupError`` -> 500) — a misconfiguration, NOT a 403 auth denial and NOT
    an ``authz.policy.denied`` event. The 500 is only a runtime backstop; the
    ``auth_spec`` startup contract check is the real guard (it ERRORs on any
    referenced policy name that is not registered).
    """
    if meta is None:
        return

    spec = normalize_auth_spec(meta.auth)
    if spec is None:
        return

    from chirp.middleware.auth import get_user

    await enforce_auth(spec, request, get_user(), policy_resolver=policy_resolver)
