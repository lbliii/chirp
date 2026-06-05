"""No-JS progressive-enhancement floor contract.

Chirp's structural advantage over diff-push UIs is that a mutating route can
serve BOTH htmx fragments (when ``HX-Request`` is present) AND a plain-POST
fallback (a 303 redirect or full-page render) — so the app works with
JavaScript disabled. ``FormAction``/``MutationResult`` and ``Redirect``/``Page``
provide that fallback; a route whose only success return is a ``Fragment`` or
``OOB`` swap silently breaks with JS off.

This check is a best-effort static heuristic over handler source AND htmx-only
mutation is a legitimate design choice, so it is INFO by default (category
``nojs_floor``). Apps that commit to the progressive-enhancement floor promote
it with ``app.override_contract_severity("nojs_floor", Severity.ERROR)``.
"""

import inspect
from typing import TYPE_CHECKING

from chirp.contracts.types import ContractIssue, Severity

if TYPE_CHECKING:
    from chirp.routing.router import Router

_MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Returns that provide a no-JS fallback (full page or 303 redirect for plain
# POST). MutationResult is the canonical class; FormAction is its alias.
_FALLBACK_RETURNS = ("FormAction", "MutationResult", "Redirect", "Page(", "Template(")

# htmx-only success returns — fine *with* a fallback, a footgun without one.
_HTMX_ONLY_RETURNS = ("Fragment(", "OOB(")


def check_nojs_mutation_fallback(router: Router) -> list[ContractIssue]:
    """Warn when a mutating route's only success path is an htmx fragment.

    Flags routes that (a) accept a mutating method, (b) are not
    ``referenced=True`` (excluded transport endpoints), and (c) return a
    ``Fragment``/``OOB`` but no ``FormAction``/``Redirect``/``Page``/``Template``
    fallback. Such a route is dead with JavaScript disabled.
    """
    issues: list[ContractIssue] = []

    for route in getattr(router, "routes", []):
        methods = getattr(route, "methods", set())
        if not (_MUTATING_METHODS & set(methods)):
            continue
        if getattr(route, "referenced", False):
            continue

        handler = route.handler
        try:
            src = inspect.getsource(handler)
        except TypeError, OSError:
            continue

        returns_htmx_only = any(token in src for token in _HTMX_ONLY_RETURNS)
        has_fallback = any(token in src for token in _FALLBACK_RETURNS)

        if returns_htmx_only and not has_fallback:
            issues.append(
                ContractIssue(
                    severity=Severity.INFO,
                    category="nojs_floor",
                    message=(
                        f"Mutating route '{route.path}' returns only htmx "
                        f"fragments (Fragment/OOB) with no no-JS fallback — it "
                        f"has no success path with JavaScript disabled. If your "
                        f"app commits to the progressive-enhancement floor, "
                        f"return FormAction (303 for plain POST, fragments for "
                        f"htmx) and promote this category to WARNING/ERROR via "
                        f'app.override_contract_severity("nojs_floor", '
                        f"Severity.ERROR). Informational by default because "
                        f"htmx-only mutation is a legitimate design choice."
                    ),
                    route=route.path,
                )
            )

    return issues
