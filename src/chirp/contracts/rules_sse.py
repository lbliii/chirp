"""SSE contract cross-checks."""

import re

from chirp.routing.router import Router

from .declarations import SSEContract
from .routes import path_matches_route
from .types import ContractIssue, Severity

_SSE_CONNECT_TAG_PATTERN = re.compile(
    r"<(?P<tag>\w+)\b(?P<attrs>[^>]*\bsse-connect\s*=\s*[\"'](?P<url>[^\"']+)[\"'][^>]*)>",
    re.IGNORECASE,
)
_SSE_SWAP_VALUE_PATTERN = re.compile(r'\bsse-swap\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
_KIDA_EXPR_PATTERN = re.compile(r"\{\{[^}]+\}\}")


def normalize_sse_url(url: str) -> str:
    """Replace Kida expressions so route-pattern matching still works."""
    return _KIDA_EXPR_PATTERN.sub("__p__", url).strip()


def extract_sse_swap_values(source: str) -> set[str]:
    """Extract all sse-swap event names from source."""
    return {match.group(1) for match in _SSE_SWAP_VALUE_PATTERN.finditer(source)}


def check_sse_self_swap(template_sources: dict[str, str]) -> list[ContractIssue]:
    """Error when sse-swap appears on same element as sse-connect."""
    issues: list[ContractIssue] = []
    for template_name, source in template_sources.items():
        for match in _SSE_CONNECT_TAG_PATTERN.finditer(source):
            attrs_lower = match.group("attrs").lower()
            if "sse-swap" not in attrs_lower:
                continue
            swap_match = _SSE_SWAP_VALUE_PATTERN.search(match.group("attrs"))
            swap_value = swap_match.group(1) if swap_match else "?"
            issues.append(
                ContractIssue(
                    severity=Severity.ERROR,
                    category="sse_self_swap",
                    message=(
                        f'sse-swap="{swap_value}" on the same element as '
                        "sse-connect will never match. htmx uses querySelectorAll "
                        "which excludes the root element. Move sse-swap to a child element."
                    ),
                    template=template_name,
                )
            )
    return issues


def check_sse_connect_scope(
    template_sources: dict[str, str],
    broad_targets: set[str],
) -> list[ContractIssue]:
    """Warn when sse-connect is inside broad hx-target scope without mitigation."""
    if not broad_targets:
        return []
    issues: list[ContractIssue] = []
    targets_text = ", ".join(sorted(broad_targets))
    for template_name, source in template_sources.items():
        if template_name.startswith("chirp/"):
            continue
        for match in _SSE_CONNECT_TAG_PATTERN.finditer(source):
            attrs_lower = match.group("attrs").lower()
            if "hx-disinherit" in attrs_lower:
                continue
            if 'hx-target="this"' in attrs_lower or "hx-target='this'" in attrs_lower:
                continue
            issues.append(
                ContractIssue(
                    severity=Severity.ERROR,
                    category="sse_scope",
                    message=(
                        "sse-connect element is inside a broad hx-target scope "
                        'without mitigation. Add hx-target="this" (safe_target '
                        "middleware auto-injects this), or hx-disinherit="
                        '"hx-target hx-swap" on sse-connect. Use '
                        '{% from "chirp/sse.html" import sse_scope %} {{ sse_scope(url) }}.'
                    ),
                    template=template_name,
                    details=f"Inherited broad target(s): {targets_text}",
                )
            )
            break
    return issues


def check_sse_event_crossref(
    template_sources: dict[str, str],
    router: Router,
) -> list[ContractIssue]:
    """Cross-reference sse-swap values against SSEContract.event_types."""
    issues: list[ContractIssue] = []
    sse_routes: dict[str, SSEContract] = {}
    for route in router.routes:
        contract = getattr(route.handler, "_chirp_contract", None)
        if (
            contract is not None
            and isinstance(contract.returns, SSEContract)
            and contract.returns.event_types
        ):
            sse_routes[route.path] = contract.returns
    if not sse_routes:
        return issues

    for template_name, source in template_sources.items():
        swap_values = extract_sse_swap_values(source)
        if not swap_values:
            continue
        for connect_match in _SSE_CONNECT_TAG_PATTERN.finditer(source):
            raw_url = connect_match.group("url")
            url = normalize_sse_url(raw_url)
            matched_route: str | None = None
            matched_contract: SSEContract | None = None
            for route_path, sse_contract in sse_routes.items():
                if path_matches_route(url, route_path):
                    matched_route = route_path
                    matched_contract = sse_contract
                    break
            if matched_contract is None or matched_route is None:
                continue

            declared = matched_contract.event_types
            undeclared = swap_values - declared
            issues.extend(
                ContractIssue(
                    severity=Severity.WARNING,
                    category="sse_crossref",
                    message=(
                        f'sse-swap="{event_name}" listens for an event that '
                        f"route '{matched_route}' does not declare in "
                        "SSEContract.event_types. Possible typo or missing "
                        "event_types entry."
                    ),
                    template=template_name,
                    route=matched_route,
                    details=f"Declared event_types: {', '.join(sorted(declared))}",
                )
                for event_name in sorted(undeclared)
            )

            unlistened = declared - swap_values
            issues.extend(
                ContractIssue(
                    severity=Severity.INFO,
                    category="sse_crossref",
                    message=(
                        f"SSE route '{matched_route}' declares event type "
                        f"'{event_name}' but no sse-swap in '{template_name}' "
                        "listens for it. The event may be unused or consumed elsewhere."
                    ),
                    template=template_name,
                    route=matched_route,
                )
                for event_name in sorted(unlistened)
            )
    return issues
