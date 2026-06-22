"""Middleware chain report — a diagnostic of the resolved request pipeline.

``App.add_middleware(mw, priority=...)`` resolves the user middleware to a
deterministic order at freeze (stable sort by ``(priority, registration)``; see
``chirp.middleware.ordering``). This check emits a single INFO line naming the
resolved **user** middleware order (outermost → innermost) so app authors can
confirm the pipeline they registered is the pipeline that runs — especially once
explicit ``priority=`` values reorder it away from registration order.

It is a **diagnostic only**: it never reports the ordering-invariant ERROR.
``CSRFMiddleware`` placed outside ``SessionMiddleware`` is still caught by the
existing ``csrf_session`` ERROR (``rules_safety.check_csrf_session_order``) and
by the hard ``ConfigurationError`` floor in ``compiler._validate_middleware_ordering``.
Keeping this category INFO avoids double-reporting that violation under a new
severity.
"""

from typing import Any

from chirp.contracts.types import ContractIssue, Severity
from chirp.middleware.ordering import sort_user_middleware


def check_middleware_chain(
    middleware_list: list[Any],
    priorities: list[int] | None,
) -> list[ContractIssue]:
    """Report the resolved user-middleware order as a single INFO diagnostic.

    Mirrors the freeze-time sort so the reported order matches the runtime
    chain. Emits nothing when no user middleware is registered (an app with only
    builtin middleware has no user pipeline to report).
    """
    if not middleware_list:
        return []

    resolved = sort_user_middleware(middleware_list, priorities)
    names = [type(mw).__name__ for mw in resolved]
    chain = " → ".join(names)

    return [
        ContractIssue(
            severity=Severity.INFO,
            category="middleware_chain",
            message=(
                f"Resolved middleware chain (outermost → innermost): {chain}. "
                "Order is sorted by add_middleware(priority=) then registration "
                "order; lower priority runs outermost. Builtin middleware "
                "(allowed-hosts, CSP nonce, security headers, injection) wraps "
                "this user chain and is not shown."
            ),
        )
    ]
