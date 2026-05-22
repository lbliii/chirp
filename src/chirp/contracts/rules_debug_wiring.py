"""Contract checks for native debug runtime wiring."""

from __future__ import annotations

from chirp.app.state import RuntimeDebugWiring
from chirp.contracts.types import ContractIssue, Severity


def check_debug_wiring(wiring: RuntimeDebugWiring) -> list[ContractIssue]:
    """Validate internal/debug runtime descriptor consistency."""
    issues: list[ContractIssue] = []
    route_by_path = {route.path: route for route in wiring.routes}
    seen_paths: set[str] = set()
    for route in wiring.routes:
        if route.path in seen_paths:
            issues.append(
                ContractIssue(
                    severity=Severity.ERROR,
                    category="debug_wiring",
                    message=f"Internal route {route.path!r} is registered more than once.",
                    route=route.path,
                )
            )
        seen_paths.add(route.path)

    for feature in wiring.features:
        if not feature.enabled:
            continue
        for path in feature.route_paths:
            route = route_by_path.get(path)
            if route is None:
                issues.append(
                    ContractIssue(
                        severity=Severity.ERROR,
                        category="debug_wiring",
                        message=(
                            f"Debug feature {feature.name!r} references internal route "
                            f"{path!r}, but no route spec owns that path."
                        ),
                        route=path,
                    )
                )
            elif not route.enabled:
                issues.append(
                    ContractIssue(
                        severity=Severity.ERROR,
                        category="debug_wiring",
                        message=(
                            f"Debug feature {feature.name!r} is enabled but route "
                            f"{path!r} is disabled."
                        ),
                        route=path,
                    )
                )
        for injection in feature.injections:
            if injection.asset_path is None:
                continue
            route = route_by_path.get(injection.asset_path)
            if route is None or not route.enabled:
                issues.append(
                    ContractIssue(
                        severity=Severity.ERROR,
                        category="debug_wiring",
                        message=(
                            f"Debug injection {injection.name!r} points at "
                            f"{injection.asset_path!r}, but that internal route is not enabled."
                        ),
                        route=injection.asset_path,
                    )
                )
            if not injection.skip_htmx:
                issues.append(
                    ContractIssue(
                        severity=Severity.ERROR,
                        category="debug_wiring",
                        message=(
                            f"Debug injection {injection.name!r} must skip htmx responses "
                            "so fragments do not boot DevTools again."
                        ),
                        route=injection.asset_path,
                    )
                )
    return issues
