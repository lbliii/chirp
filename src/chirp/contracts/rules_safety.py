"""Safety contract checks — catch silent failures that app.check() previously missed.

Categories:
- ``sse_speculation``: SSE/streaming routes without speculation exclusion
- ``csrf_session``: CSRFMiddleware without SessionMiddleware
- ``middleware_signature``: Middleware with wrong call signature
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any

from chirp.contracts.types import ContractIssue, Severity

if TYPE_CHECKING:
    from chirp.routing.router import Router


# ---------------------------------------------------------------------------
# SSE routes without speculation exclusion
# ---------------------------------------------------------------------------

_SSE_INDICATORS = frozenset({"EventStream", "reactive_stream"})


def check_sse_speculation(
    router: Router,
) -> list[ContractIssue]:
    """Warn when SSE/streaming routes lack ``referenced=True``.

    SSE endpoints included in browser speculation rules cause silent
    prefetch connections that hang.  Routes whose handler source contains
    ``EventStream`` or ``reactive_stream`` should set ``referenced=True``
    to be excluded from speculation.
    """
    issues: list[ContractIssue] = []

    for route in getattr(router, "routes", []):
        if getattr(route, "referenced", False):
            continue

        # Check if handler or its contract hints at SSE
        handler = route.handler
        contract = getattr(handler, "_chirp_contract", None)
        returns = getattr(contract, "returns", None)

        # SSEContract is a strong signal
        from chirp.contracts.declarations import SSEContract

        if isinstance(returns, SSEContract):
            issues.append(
                ContractIssue(
                    severity=Severity.WARNING,
                    category="sse_speculation",
                    message=(
                        f"SSE route '{route.path}' does not set "
                        f"referenced=True — it will be included in "
                        f"browser speculation/prefetch rules. Add "
                        f"referenced=True to the route decorator."
                    ),
                    route=route.path,
                )
            )
            continue

        # Fallback: inspect handler source for EventStream usage
        try:
            src = inspect.getsource(handler)
        except TypeError, OSError:
            continue
        if any(indicator in src for indicator in _SSE_INDICATORS):
            issues.append(
                ContractIssue(
                    severity=Severity.WARNING,
                    category="sse_speculation",
                    message=(
                        f"Route '{route.path}' appears to return an "
                        f"EventStream but does not set referenced=True — "
                        f"it may be included in browser speculation rules. "
                        f"Add referenced=True to exclude it."
                    ),
                    route=route.path,
                )
            )

    return issues


# ---------------------------------------------------------------------------
# CSRF without SessionMiddleware
# ---------------------------------------------------------------------------


def check_csrf_session_order(
    middleware_list: list[Any],
) -> list[ContractIssue]:
    """Error when CSRFMiddleware is registered without SessionMiddleware.

    CSRF tokens are stored in the session.  If SessionMiddleware is missing
    or ordered after CSRFMiddleware, CSRF validation will fail at request
    time with a confusing error.
    """
    issues: list[ContractIssue] = []

    csrf_index: int | None = None
    session_index: int | None = None

    for i, mw in enumerate(middleware_list):
        cls_name = type(mw).__name__
        if cls_name == "CSRFMiddleware":
            csrf_index = i
        elif cls_name == "SessionMiddleware":
            session_index = i

    if csrf_index is not None and session_index is None:
        issues.append(
            ContractIssue(
                severity=Severity.ERROR,
                category="csrf_session",
                message=(
                    "CSRFMiddleware is registered but SessionMiddleware is "
                    "missing. CSRF tokens are stored in the session — add "
                    "SessionMiddleware before CSRFMiddleware."
                ),
            )
        )
    elif csrf_index is not None and session_index is not None and session_index > csrf_index:
        issues.append(
            ContractIssue(
                severity=Severity.WARNING,
                category="csrf_session",
                message=(
                    "SessionMiddleware is registered after CSRFMiddleware. "
                    "The session may not be available when CSRF validation "
                    "runs. Move SessionMiddleware before CSRFMiddleware."
                ),
            )
        )

    return issues


# ---------------------------------------------------------------------------
# Middleware signature validation
# ---------------------------------------------------------------------------


def check_middleware_signatures(
    middleware_list: list[Any],
) -> list[ContractIssue]:
    """Warn when middleware has a ``__call__`` signature that won't work.

    Chirp middleware must be async callables accepting ``(request, next)``
    and returning a response.  Wrong signatures crash at request time with
    confusing tracebacks.
    """
    issues: list[ContractIssue] = []

    for mw in middleware_list:
        if not callable(mw):
            issues.append(
                ContractIssue(
                    severity=Severity.ERROR,
                    category="middleware_signature",
                    message=(
                        f"Middleware {type(mw).__name__!r} is not callable. "
                        f"Middleware must implement __call__(self, request, next)."
                    ),
                )
            )
            continue

        call_method = mw.__call__
        try:
            sig = inspect.signature(call_method)
        except ValueError, TypeError:
            continue  # Can't inspect — skip

        # Filter out 'self' for bound methods
        params = [
            p
            for name, p in sig.parameters.items()
            if name != "self"
            and p.kind
            in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            )
        ]

        if len(params) < 2:
            issues.append(
                ContractIssue(
                    severity=Severity.ERROR,
                    category="middleware_signature",
                    message=(
                        f"Middleware {type(mw).__name__!r} __call__ accepts "
                        f"{len(params)} positional parameter(s), expected 2 "
                        f"(request, next). It will fail at request time."
                    ),
                )
            )
            continue

        if not inspect.iscoroutinefunction(call_method):
            issues.append(
                ContractIssue(
                    severity=Severity.WARNING,
                    category="middleware_signature",
                    message=(
                        f"Middleware {type(mw).__name__!r} __call__ is not "
                        f"async. Chirp middleware should be async def "
                        f"__call__(self, request, next)."
                    ),
                )
            )

    return issues
