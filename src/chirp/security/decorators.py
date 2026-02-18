"""Route protection decorators — @login_required and @requires.

Content-negotiated responses:
- Browser requests → redirect to login URL (302)
- API requests → JSON error (401/403)

Detection heuristic: a request is considered an API request if it
has an ``Authorization`` header or its ``Accept`` header prefers JSON
over HTML.

Usage::

    from chirp.security import login_required, requires

    @app.route("/dashboard")
    @login_required
    def dashboard():
        return Template("dashboard.html")

    @app.route("/admin")
    @requires("admin")
    def admin_panel():
        return Template("admin.html")
"""

import logging
from collections.abc import Awaitable, Callable
from functools import wraps
from inspect import isawaitable
from typing import Any
from urllib.parse import quote

from chirp._internal.invoke import invoke
from chirp.errors import HTTPError
from chirp.security.audit import emit_security_event

_log = logging.getLogger("chirp.security")


def _is_api_request(request: Any) -> bool:
    """Detect whether the request is from an API client (not a browser).

    Heuristic:
    - Has ``Authorization`` header → API client
    - ``Accept`` prefers JSON over HTML → API client
    - Otherwise → browser
    """
    if request.headers.get("authorization"):
        return True

    accept = request.headers.get("accept", "")
    # If accept explicitly mentions json but not html, treat as API
    has_json = "application/json" in accept
    has_html = "text/html" in accept
    return bool(has_json and not has_html)


def login_required(handler: Callable) -> Callable:
    """Require an authenticated user to access this route.

    Browser requests are redirected to the login URL (from ``AuthConfig``).
    API requests receive a 401 response.

    Usage::

        @app.route("/dashboard")
        @login_required
        def dashboard():
            return Template("dashboard.html")
    """

    @wraps(handler)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        from chirp.context import get_request
        from chirp.middleware.auth import _active_config, get_user

        user = get_user()
        if not user.is_authenticated:
            request = get_request()
            if _is_api_request(request):
                emit_security_event("auth.require.unauthenticated", request=request)
                raise HTTPError(status=401, detail="Authentication required")

            config = _active_config.get()
            login_url = config.login_url if config else "/login"
            if login_url:
                next_url = quote(request.url, safe="")
                separator = "&" if "?" in login_url else "?"
                redirect_url = f"{login_url}{separator}next={next_url}"
                raise HTTPError(
                    status=302,
                    detail="Login required",
                    headers=(("Location", redirect_url),),
                )
            emit_security_event("auth.require.unauthenticated", request=request)
            raise HTTPError(status=401, detail="Authentication required")

        return await invoke(handler, *args, **kwargs)

    return wrapper


def requires(
    *permissions: str,
    policy: Callable[[Any, Any], bool | Awaitable[bool]] | None = None,
) -> Callable:
    """Require specific permissions to access this route.

    Returns 401 if not authenticated, 403 if missing permissions.

    Usage::

        @app.route("/admin")
        @requires("admin")
        def admin_panel():
            return Template("admin.html")

        @app.route("/edit")
        @requires("editor", "moderator")  # needs ALL listed permissions
        def edit_post():
            return Template("edit.html")
    """

    def decorator(handler: Callable) -> Callable:
        @wraps(handler)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            from chirp.context import get_request
            from chirp.middleware.auth import UserWithPermissions, _active_config, get_user

            user = get_user()
            if not user.is_authenticated:
                request = get_request()
                if _is_api_request(request):
                    emit_security_event("auth.require.unauthenticated", request=request)
                    raise HTTPError(status=401, detail="Authentication required")

                config = _active_config.get()
                login_url = config.login_url if config else "/login"
                if login_url:
                    next_url = quote(request.url, safe="")
                    separator = "&" if "?" in login_url else "?"
                    redirect_url = f"{login_url}{separator}next={next_url}"
                    raise HTTPError(
                        status=302,
                        detail="Login required",
                        headers=(("Location", redirect_url),),
                    )
                emit_security_event("auth.require.unauthenticated", request=request)
                raise HTTPError(status=401, detail="Authentication required")

            # Check permissions
            if not isinstance(user, UserWithPermissions):
                _log.warning(
                    "User %s model does not implement permissions protocol",
                    user.id,
                )
                emit_security_event(
                    "authz.permission.denied",
                    user_id=user.id,
                    details={"reason": "missing_permissions_protocol"},
                )
                raise HTTPError(status=403, detail="Forbidden")

            required = frozenset(permissions)
            if not required.issubset(user.permissions):
                missing = required - user.permissions
                _log.warning(
                    "User %s missing permissions: %s",
                    user.id,
                    ", ".join(sorted(missing)),
                )
                emit_security_event(
                    "authz.permission.denied",
                    user_id=user.id,
                    details={"missing": sorted(missing)},
                )
                raise HTTPError(status=403, detail="Forbidden")

            if policy is not None:
                request = get_request()
                allowed = policy(user, request)
                if isawaitable(allowed):
                    allowed = await allowed
                if not allowed:
                    emit_security_event(
                        "authz.policy.denied",
                        request=request,
                        user_id=user.id,
                        details={"policy": getattr(policy, "__name__", "custom_policy")},
                    )
                    raise HTTPError(status=403, detail="Forbidden")

            return await invoke(handler, *args, **kwargs)

        return wrapper

    return decorator
