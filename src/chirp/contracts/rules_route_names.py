"""Route-name collision contract check.

``Route.name`` is now populated for every page-discovered route (see
``chirp.pages.discovery.default_route_name``). ``app.url_for(name, ...)``
returns an unpredictable URL if two routes claim the same name — so we
surface duplicates as contract issues instead of letting the last-write
winner leak into production.

Severity defaults to ``ERROR`` and can be tuned via
``app.override_contract_severity("route_names", Severity.WARNING)``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .types import ContractIssue, Severity

if TYPE_CHECKING:
    from chirp.routing.route import Route


def check_route_names(
    collisions: dict[str, list[Route]],
) -> list[ContractIssue]:
    """Emit one ERROR issue per duplicated route name."""
    issues: list[ContractIssue] = []
    for name, routes in collisions.items():
        summary = ", ".join(
            f"{sorted(r.methods)[0] if r.methods else '-'} {r.path}" for r in routes
        )
        issues.append(
            ContractIssue(
                severity=Severity.ERROR,
                category="route_names",
                message=(
                    f"Duplicate route name {name!r} used by {len(routes)} routes: "
                    f"{summary}. Rename one of them or set a module-level "
                    f"`name` attribute on the page file(s)."
                ),
            )
        )
    return issues
