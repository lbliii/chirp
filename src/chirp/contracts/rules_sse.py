"""SSE contract cross-checks."""

import ast
import inspect
import re
import textwrap
from typing import Any

from chirp.routing.router import Router

from .declarations import SSEContract
from .patterns import KIDA_EXPR as _KIDA_EXPR_PATTERN
from .patterns import SSE_CONNECT_TAG as _SSE_CONNECT_TAG_PATTERN
from .routes import build_route_index, find_matching_route
from .types import ContractIssue, Severity

_SSE_SWAP_VALUE_PATTERN = re.compile(r'\bsse-swap\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)


def normalize_sse_url(url: str) -> str:
    """Replace Kida expressions so route-pattern matching still works."""
    return _KIDA_EXPR_PATTERN.sub("__p__", url).strip()


def extract_sse_swap_values(source: str) -> set[str]:
    """Extract all sse-swap event names from source."""
    return {match.group(1) for match in _SSE_SWAP_VALUE_PATTERN.finditer(source)}


def _call_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _string_kwarg(node: ast.Call, name: str) -> tuple[bool, str | None]:
    """Return ``(confident, value)`` for a string keyword argument."""
    for kw in node.keywords:
        if kw.arg != name:
            continue
        if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
            return True, kw.value.value
        if isinstance(kw.value, ast.Constant) and kw.value.value is None:
            return True, None
        return False, None
    return True, None


def _infer_emitted_events(handler: Any) -> set[str] | None:
    """Infer literal SSE event names emitted by a route handler.

    Returns ``None`` when source is unavailable or a relevant event name is
    dynamic. Dynamic cases are skipped by the cross-reference check so the
    contract errs toward silence instead of false positives.
    """
    try:
        source = inspect.getsource(inspect.unwrap(handler))
        tree = ast.parse(textwrap.dedent(source))
    except (OSError, SyntaxError, TypeError):
        return None

    emitted: set[str] = set()
    saw_sse_call = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func_name = _call_name(node.func)
        if func_name == "SSEEvent":
            saw_sse_call = True
            confident, value = _string_kwarg(node, "event")
            if not confident:
                return None
            emitted.add(value or "message")
        elif func_name == "Fragment":
            saw_sse_call = True
            confident, value = _string_kwarg(node, "target")
            if not confident:
                return None
            emitted.add(value or "message")

    return emitted if saw_sse_call else set()


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
    """Cross-reference sse-swap values against declared and inferred events."""
    issues: list[ContractIssue] = []
    sse_routes: dict[str, tuple[frozenset[str], set[str] | None]] = {}
    for route in router.routes:
        contract = getattr(route.handler, "_chirp_contract", None)
        declared = frozenset()
        if (
            contract is not None
            and isinstance(contract.returns, SSEContract)
        ):
            declared = contract.returns.event_types
        inferred = _infer_emitted_events(route.handler)
        if declared or inferred:
            sse_routes[route.path] = (declared, inferred)
    if not sse_routes:
        return issues

    # Pre-segment for O(1) static / O(parametric) URL matching
    route_paths = {path: frozenset() for path in sse_routes}
    static_routes, parametric_routes = build_route_index(route_paths)

    for template_name, source in template_sources.items():
        swap_values = extract_sse_swap_values(source)
        if not swap_values:
            continue
        for connect_match in _SSE_CONNECT_TAG_PATTERN.finditer(source):
            raw_url = connect_match.group("url")
            url = normalize_sse_url(raw_url)
            match = find_matching_route(url, static_routes, parametric_routes)
            if match is None:
                continue
            matched_route, _ = match
            declared, inferred = sse_routes[matched_route]

            known = set(declared)
            if inferred is not None:
                known.update(inferred)
            undeclared = swap_values - known
            severity = Severity.INFO if inferred is None and not declared else Severity.ERROR
            issues.extend(
                ContractIssue(
                    severity=severity,
                    category="sse_crossref",
                    message=(
                        f'sse-swap="{event_name}" listens for an event that '
                        f"route '{matched_route}' does not emit or declare. "
                        "Possible typo or missing SSEContract.event_types entry."
                    ),
                    template=template_name,
                    route=matched_route,
                    details=(
                        f"Declared event_types: {', '.join(sorted(declared)) or '(none)'}; "
                        f"Inferred event types: "
                        f"{', '.join(sorted(inferred)) if inferred is not None else '(dynamic)'}"
                    ),
                )
                for event_name in sorted(undeclared)
            )

            unlistened = set(declared) - swap_values
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
