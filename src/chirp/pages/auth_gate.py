"""Declarative auth enforcement from filesystem route metadata."""

from __future__ import annotations

from chirp.errors import HTTPError
from chirp.http.request import Request
from chirp.pages.types import RouteMeta
from chirp.security.audit import emit_security_event
from chirp.security.decorators import (
    _build_login_redirect,
    _is_api_request,
    _next_url_for_request,
)


async def enforce_route_meta_auth(meta: RouteMeta | None, request: Request) -> None:
    """Enforce ``RouteMeta.auth`` before a mounted page handler runs.

    Supported values:

    - ``None``, ``"none"``, ``"optional"`` — no gate
    - ``"required"`` — authenticated user required (browser redirect or 401)
    - any other string — treated as a single required permission via
      ``UserWithPermissions.permissions``
    """
    if meta is None or not meta.auth:
        return

    auth_spec = meta.auth
    if auth_spec in ("none", "optional"):
        return

    from chirp.middleware.auth import UserWithPermissions, _active_config, get_user

    user = get_user()
    if not user.is_authenticated:
        if _is_api_request(request):
            emit_security_event("auth.require.unauthenticated", request=request)
            raise HTTPError(status=401, detail="Authentication required")

        config = _active_config.get()
        login_url = config.login_url if config else "/login"
        if login_url:
            redirect_url = _build_login_redirect(login_url, _next_url_for_request(request))
            raise HTTPError(
                status=302,
                detail="Login required",
                headers=(("Location", redirect_url),),
            )
        emit_security_event("auth.require.unauthenticated", request=request)
        raise HTTPError(status=401, detail="Authentication required")

    if auth_spec == "required":
        return

    if not isinstance(user, UserWithPermissions):
        emit_security_event(
            "authz.permission.denied",
            user_id=user.id,
            details={"reason": "missing_permissions_protocol", "required": auth_spec},
        )
        raise HTTPError(status=403, detail="Forbidden")

    if auth_spec not in user.permissions:
        emit_security_event(
            "authz.permission.denied",
            user_id=user.id,
            details={"required": auth_spec, "missing": auth_spec},
        )
        raise HTTPError(status=403, detail="Forbidden")
