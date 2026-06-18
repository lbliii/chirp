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

from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any

from chirp._internal.invoke import invoke
from chirp.pages.types import AuthSpec
from chirp.security.auth_core import (
    _build_login_redirect,
    _is_api_request,
    _next_url_for_request,
    enforce_auth,
)

# Re-exported for back-compat: ``chirp.pages.auth_gate`` and tests historically
# import these helpers from this module. The canonical home is now
# ``chirp.security.auth_core``.
__all__ = [
    "_build_login_redirect",
    "_is_api_request",
    "_next_url_for_request",
    "login_required",
    "requires",
]


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
        from chirp.middleware.auth import get_user

        # Authn-only: AuthSpec with no permissions and no policy. Delegates to
        # the one shared gate so the unauthenticated outcome + audit event match
        # the declarative path exactly.
        await enforce_auth(AuthSpec(), get_request(), get_user())

        return await invoke(handler, *args, **kwargs)

    # Static, introspectable marker so a contract check can prove this route is
    # auth-gated WITHOUT executing the handler. @wraps copies __wrapped__, so
    # inspect.unwrap reaches the inner handler while this marker stays on the
    # outermost wrapper the router stores. Framework-internal (single leading
    # underscore, no name-mangling).
    wrapper._chirp_requires_auth = True  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]

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

    # Build the structured spec once (the public signature is unchanged). A
    # callable ``policy`` keeps working: we name it by ``__name__`` (preserving
    # the historical ``details={"policy": <name>}`` audit payload) and hand the
    # core a resolver that maps that name back to the live callable, so the core
    # stays registry-agnostic and identical for both gate paths.
    policy_name = getattr(policy, "__name__", "custom_policy") if policy is not None else None
    spec = AuthSpec(permissions=tuple(permissions), mode="all", policy=policy_name)

    def _policy_resolver(name: str) -> Callable[[Any, Any], bool | Awaitable[bool]] | None:
        return policy if name == policy_name else None

    def decorator(handler: Callable) -> Callable:
        @wraps(handler)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            from chirp.context import get_request
            from chirp.middleware.auth import get_user

            await enforce_auth(spec, get_request(), get_user(), policy_resolver=_policy_resolver)

            return await invoke(handler, *args, **kwargs)

        # Static, introspectable marker so a contract check can prove this route
        # is auth-gated WITHOUT executing the handler. @wraps copies __wrapped__,
        # so inspect.unwrap reaches the inner handler while this marker stays on
        # the outermost wrapper the router stores. Framework-internal (single
        # leading underscore, no name-mangling).
        wrapper._chirp_requires_auth = True  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]

        return wrapper

    return decorator
