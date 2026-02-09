"""Typed hypermedia contracts — compile-time validation of the server-client surface.

Validates that the hypermedia surface is internally consistent:
every ``hx-get``, ``hx-post``, ``action`` attribute in templates
resolves to a registered route, and every Fragment/SSE return type
references a valid template and block.

This gives Chirp something React/Next.js doesn't have: compile-time
validation of the full server-client boundary without JavaScript.

Usage::

    # In development, validate on startup:
    app._ensure_frozen()
    issues = check_hypermedia_surface(app)
    for issue in issues:
        print(f"{issue.severity}: {issue.message}")

    # Or via CLI:
    #   chirp check

"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from chirp.app import App
    from chirp.routing.router import Router

# ---------------------------------------------------------------------------
# Issue types
# ---------------------------------------------------------------------------


class Severity(Enum):
    """Severity of a contract validation issue."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True, slots=True)
class ContractIssue:
    """A single validation issue found during contract checking."""

    severity: Severity
    category: str
    message: str
    template: str | None = None
    route: str | None = None
    details: str | None = None


# ---------------------------------------------------------------------------
# Contract declarations (for route metadata)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FragmentContract:
    """Declares that a route returns a specific template fragment.

    Used for documentation and validation.  Chirp verifies at freeze
    time that the template and block exist.

    """

    template: str
    block: str


@dataclass(frozen=True, slots=True)
class SSEContract:
    """Declares the event types an SSE endpoint emits.

    Used for documentation and validation.

    """

    event_types: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class RouteContract:
    """Full contract metadata for a route.

    Attached to routes via the ``contract`` parameter on ``@app.route()``.

    """

    returns: FragmentContract | SSEContract | None = None
    description: str = ""


# ---------------------------------------------------------------------------
# Template scanner — extract htmx targets from template AST
# ---------------------------------------------------------------------------

# htmx attributes that reference server URLs
_HTMX_URL_ATTRS = frozenset({
    "hx-get", "hx-post", "hx-put", "hx-patch", "hx-delete",
})

# Regex to extract htmx/form attributes from raw template HTML
# Matches: hx-get="/path" or action="/path"
_ATTR_PATTERN = re.compile(
    r'(?:hx-(?:get|post|put|patch|delete)|action)\s*=\s*["\']([^"\']*)["\']',
)


def _extract_targets_from_source(source: str) -> list[tuple[str, str]]:
    """Extract (attr_name, url) pairs from template source text.

    Scans raw template source for htmx URL attributes and form actions.
    This catches static URLs in HTML; dynamic URLs (from template expressions)
    are not captured and should be validated separately.

    """
    targets: list[tuple[str, str]] = []
    for match in re.finditer(
        r'(hx-(?:get|post|put|patch|delete)|action)\s*=\s*["\']([^"\']*)["\']',
        source,
    ):
        attr_name = match.group(1)
        url = match.group(2)
        # Skip template expressions ({{ ... }}) and anchors
        if "{{" in url or url.startswith("#") or url.startswith("javascript:"):
            continue
        targets.append((attr_name, url))
    return targets


# ---------------------------------------------------------------------------
# hx-target selector scanner — cross-reference against element IDs
# ---------------------------------------------------------------------------

# Regex: hx-target="..." values (ID selectors, extended selectors, keywords)
_HX_TARGET_PATTERN = re.compile(
    r'hx-target\s*=\s*["\']([^"\']*)["\']',
)

# Regex: static id="..." values in HTML
_ID_PATTERN = re.compile(
    r'\bid\s*=\s*["\']([^"\']*)["\']',
)

# htmx extended CSS selectors — traversal-based, not validatable statically
_HTMX_EXTENDED_PREFIXES = frozenset({
    "closest", "find", "next", "previous",
})

# htmx special target keywords that don't reference a DOM element by ID
_HTMX_SPECIAL_TARGETS = frozenset({
    "this", "body", "window", "document",
})


def _extract_hx_target_selectors(source: str) -> list[str]:
    """Extract ``hx-target`` values from template source.

    Returns raw selector strings, skipping template expressions.
    """
    selectors: list[str] = []
    for match in _HX_TARGET_PATTERN.finditer(source):
        value = match.group(1).strip()
        # Skip template expressions
        if "{{" in value or "{%" in value:
            continue
        if value:
            selectors.append(value)
    return selectors


def _extract_static_ids(source: str) -> set[str]:
    """Extract all static ``id`` attribute values from template HTML.

    Skips IDs containing template expressions (these are dynamic and
    cannot be validated at compile time).
    """
    ids: set[str] = set()
    for match in _ID_PATTERN.finditer(source):
        value = match.group(1).strip()
        if value and "{{" not in value and "{%" not in value:
            ids.add(value)
    return ids


def _edit_distance(a: str, b: str) -> int:
    """Levenshtein distance between two strings."""
    if len(a) > len(b):
        a, b = b, a
    prev = list(range(len(a) + 1))
    for j in range(1, len(b) + 1):
        curr = [j] + [0] * len(a)
        for i in range(1, len(a) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            curr[i] = min(curr[i - 1] + 1, prev[i] + 1, prev[i - 1] + cost)
        prev = curr
    return prev[len(a)]


def _closest_id(target: str, ids: set[str], *, max_dist: int = 3) -> str | None:
    """Find the closest ID by edit distance, or ``None`` if nothing is close."""
    if not ids:
        return None
    target_lower = target.lower()
    best: str | None = None
    best_dist = max_dist + 1
    for candidate in sorted(ids):  # sorted for determinism
        dist = _edit_distance(target_lower, candidate.lower())
        if dist < best_dist:
            best_dist = dist
            best = candidate
    return best if best_dist <= max_dist else None


def _check_hx_target_selectors(
    template_sources: dict[str, str],
    all_ids: set[str],
) -> tuple[list[ContractIssue], int]:
    """Validate ``hx-target`` selectors against the pool of static element IDs.

    Only validates simple ``#id`` selectors.  Extended selectors (``closest``,
    ``find``, ``next``, ``previous``) and special keywords (``this``, ``body``)
    are skipped — they can't be validated statically.

    Returns:
        A tuple of (issues, targets_validated).
    """
    issues: list[ContractIssue] = []
    validated = 0

    for tmpl_name, source in template_sources.items():
        selectors = _extract_hx_target_selectors(source)
        for selector in selectors:
            first_word = selector.split()[0] if selector else ""

            # Skip special keywords
            if first_word.lower() in _HTMX_SPECIAL_TARGETS:
                continue
            # Skip extended traversal selectors
            if first_word.lower() in _HTMX_EXTENDED_PREFIXES:
                continue

            # Validate #id selectors
            if selector.startswith("#"):
                # Only simple selectors — no compound (#foo .bar)
                if " " in selector:
                    continue
                target_id = selector[1:]
                if not target_id:
                    continue
                validated += 1
                if target_id not in all_ids:
                    suggestion = _closest_id(target_id, all_ids)
                    hint = f' Did you mean "#{suggestion}"?' if suggestion else ""
                    issues.append(ContractIssue(
                        severity=Severity.WARNING,
                        category="hx-target",
                        message=(
                            f'hx-target="#{target_id}" — no element with '
                            f'id="{target_id}" found in any template.{hint}'
                        ),
                        template=tmpl_name,
                        details=f'Available IDs: {", ".join(sorted(all_ids)[:10])}'
                        if all_ids else None,
                    ))

    return issues, validated


# ---------------------------------------------------------------------------
# Accessibility scanner — htmx on non-interactive elements
# ---------------------------------------------------------------------------

# Elements that are natively interactive (keyboard-focusable, have roles)
_INTERACTIVE_ELEMENTS = frozenset({
    "a", "button", "input", "select", "textarea", "form", "details", "summary",
})

# Regex: capture the opening tag surrounding an hx-* URL attribute.
# Matches e.g. <div class="card" hx-get="/items" hx-target="#main">
# Group 1: tag name, Group 0: full opening tag up to the hx- attr.
_HX_TAG_PATTERN = re.compile(
    r"<(\w+)\b([^>]*?)\s+(?:hx-(?:get|post|put|patch|delete))\s*=",
    re.IGNORECASE,
)


def _check_accessibility(source: str, template_name: str) -> list[ContractIssue]:
    """Check for htmx URL attributes on non-interactive elements.

    Warns when ``hx-get``, ``hx-post``, etc. appear on elements like
    ``<div>`` or ``<span>`` without ``role`` or ``tabindex`` attributes
    that would make them accessible to keyboard and screen reader users.
    """
    issues: list[ContractIssue] = []
    for match in _HX_TAG_PATTERN.finditer(source):
        tag_name = match.group(1).lower()
        if tag_name in _INTERACTIVE_ELEMENTS:
            continue
        # Check the preceding attributes in this tag for role or tabindex
        preceding_attrs = match.group(2)
        full_tag_end = source.find(">", match.end())
        trailing_attrs = source[match.end():full_tag_end] if full_tag_end != -1 else ""
        all_attrs = preceding_attrs + " " + trailing_attrs
        has_role = "role=" in all_attrs.lower()
        has_tabindex = "tabindex=" in all_attrs.lower()
        if not has_role and not has_tabindex:
            # Find which hx- attribute triggered this
            hx_match = re.search(r"hx-(?:get|post|put|patch|delete)", all_attrs)
            hx_attr = hx_match.group(0) if hx_match else "hx-*"
            issues.append(ContractIssue(
                severity=Severity.WARNING,
                category="accessibility",
                message=(
                    f"{hx_attr} on <{tag_name}> — use <button> or <a>, "
                    f"or add role=\"button\" tabindex=\"0\" for accessibility."
                ),
                template=template_name,
            ))
    return issues


def _attr_to_method(attr: str) -> str:
    """Map an htmx attribute name to its HTTP method."""
    if attr == "action":
        return "POST"  # Default form method
    # hx-get → GET, hx-post → POST, etc.
    return attr.split("-", 1)[1].upper()


# ---------------------------------------------------------------------------
# Route introspection
# ---------------------------------------------------------------------------


def _collect_route_paths(router: Router) -> dict[str, frozenset[str]]:
    """Build a mapping of path → allowed methods from the router.

    Returns a dict where keys are route path patterns and values are
    sets of allowed HTTP methods.  Multiple routes on the same path
    have their methods merged.

    """
    path_methods: dict[str, set[str]] = {}
    for route in router.routes:
        if route.path not in path_methods:
            path_methods[route.path] = set()
        path_methods[route.path].update(route.methods)
    return {path: frozenset(methods) for path, methods in path_methods.items()}


def _path_matches_route(url: str, route_path: str) -> bool:
    """Check if a URL could match a route pattern.

    Handles static paths exactly and parameterized paths approximately
    (any path segment can match a ``{param}`` segment).

    """
    url_parts = url.strip("/").split("/")
    route_parts = route_path.strip("/").split("/")

    if len(url_parts) != len(route_parts):
        # Check for catch-all
        if route_parts and route_parts[-1].startswith("{") and ":path" in route_parts[-1]:
            return len(url_parts) >= len(route_parts) - 1
        return False

    for url_seg, route_seg in zip(url_parts, route_parts, strict=True):
        if route_seg.startswith("{") and route_seg.endswith("}"):
            continue  # Parameter — matches anything
        if url_seg != route_seg:
            return False
    return True


# ---------------------------------------------------------------------------
# Checker
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class CheckResult:
    """Result of a hypermedia surface check."""

    issues: list[ContractIssue] = field(default_factory=list)
    routes_checked: int = 0
    templates_scanned: int = 0
    targets_found: int = 0
    hx_targets_validated: int = 0

    @property
    def errors(self) -> list[ContractIssue]:
        return [i for i in self.issues if i.severity == Severity.ERROR]

    @property
    def warnings(self) -> list[ContractIssue]:
        return [i for i in self.issues if i.severity == Severity.WARNING]

    @property
    def ok(self) -> bool:
        return not self.errors

    def summary(self) -> str:
        """Human-readable summary."""
        lines = [
            f"Checked {self.routes_checked} routes, "
            f"scanned {self.templates_scanned} templates, "
            f"found {self.targets_found} hypermedia targets, "
            f"validated {self.hx_targets_validated} hx-target selectors.",
        ]
        if self.ok and not self.warnings:
            lines.append("No issues found.")
        elif self.ok:
            lines.append(f"No errors. {len(self.warnings)} warning(s).")
        else:
            lines.append(f"{len(self.errors)} error(s), {len(self.warnings)} warning(s).")
        for issue in self.issues:
            prefix = issue.severity.value.upper()
            loc = f" in {issue.template}" if issue.template else ""
            lines.append(f"  [{prefix}] {issue.message}{loc}")
            if issue.details:
                lines.append(f"           {issue.details}")
        return "\n".join(lines)


def check_hypermedia_surface(app: App) -> CheckResult:
    """Validate the hypermedia surface of a Chirp application.

    Checks:
    1. **Fragment references**: Every route with a FragmentContract
       references a template and block that exist.
    2. **htmx URL targets**: Every ``hx-get``, ``hx-post``, etc. in
       template HTML resolves to a registered route with the correct method.
    3. **Form actions**: Every ``action="/path"`` in template HTML
       resolves to a registered route.
    4. **hx-target selectors**: Every ``hx-target="#id"`` in template HTML
       references an element ID that exists somewhere in the template tree
       (warning — IDs may come from dynamic expressions or JS).
    5. **Accessibility**: htmx URL attributes on non-interactive elements
       (``<div>``, ``<span>``, etc.) without ``role`` or ``tabindex``
       (warning, not error).
    6. **Orphan routes**: Routes that are never referenced from templates
       (info, not error).

    Args:
        app: A frozen Chirp application.

    Returns:
        CheckResult with issues and statistics.

    """
    result = CheckResult()

    # Ensure app is frozen (routes compiled, templates loaded)
    app._ensure_frozen()

    router = app._router
    kida_env = app._kida_env

    if router is None:
        result.issues.append(ContractIssue(
            severity=Severity.ERROR,
            category="setup",
            message="No router available — app may not have routes.",
        ))
        return result

    # 1. Collect registered routes
    route_paths = _collect_route_paths(router)
    result.routes_checked = len(route_paths)

    # 2. Check Fragment contracts
    for route in router.routes:
        contract = getattr(route.handler, "_chirp_contract", None)
        if contract is None:
            continue

        if isinstance(contract.returns, FragmentContract):
            fc = contract.returns
            if kida_env is not None:
                try:
                    tmpl = kida_env.get_template(fc.template)
                    # Check if block exists
                    blocks = tmpl.blocks
                    if fc.block not in blocks:
                        result.issues.append(ContractIssue(
                            severity=Severity.ERROR,
                            category="fragment",
                            message=(
                                f"Route '{route.path}' declares fragment "
                                f"block '{fc.block}' but template "
                                f"'{fc.template}' has no such block."
                            ),
                            route=route.path,
                            template=fc.template,
                        ))
                except Exception:
                    result.issues.append(ContractIssue(
                        severity=Severity.ERROR,
                        category="fragment",
                        message=(
                            f"Route '{route.path}' references template "
                            f"'{fc.template}' which could not be loaded."
                        ),
                        route=route.path,
                        template=fc.template,
                    ))

    # 3. Scan templates for htmx targets and form actions
    if kida_env is not None and kida_env.loader is not None:
        template_sources = _load_template_sources(kida_env)
        result.templates_scanned = len(template_sources)

        referenced_paths: set[str] = set()

        for tmpl_name, source in template_sources.items():
            targets = _extract_targets_from_source(source)
            result.targets_found += len(targets)

            for attr_name, url in targets:
                method = _attr_to_method(attr_name)

                # Find a matching route
                matched = False
                for route_path, methods in route_paths.items():
                    if _path_matches_route(url, route_path):
                        referenced_paths.add(route_path)
                        if method not in methods:
                            result.issues.append(ContractIssue(
                                severity=Severity.ERROR,
                                category="method",
                                message=(
                                    f"'{attr_name}=\"{url}\"' uses {method} "
                                    f"but route '{route_path}' only allows "
                                    f"{', '.join(sorted(methods))}."
                                ),
                                template=tmpl_name,
                                route=route_path,
                            ))
                        matched = True
                        break

                if not matched:
                    result.issues.append(ContractIssue(
                        severity=Severity.ERROR,
                        category="target",
                        message=(
                            f"'{attr_name}=\"{url}\"' has no matching route."
                        ),
                        template=tmpl_name,
                    ))

        # 4. Check hx-target selectors against static element IDs
        all_ids: set[str] = set()
        for source in template_sources.values():
            all_ids.update(_extract_static_ids(source))
        hx_target_issues, hx_validated = _check_hx_target_selectors(
            template_sources, all_ids,
        )
        result.hx_targets_validated = hx_validated
        result.issues.extend(hx_target_issues)

        # 5. Check accessibility — htmx on non-interactive elements
        for tmpl_name, source in template_sources.items():
            a11y_issues = _check_accessibility(source, tmpl_name)
            result.issues.extend(a11y_issues)

        # 6. Check for orphan routes (routes never referenced from templates)
        for route_path in route_paths:
            if route_path not in referenced_paths and route_path != "/":
                result.issues.append(ContractIssue(
                    severity=Severity.INFO,
                    category="orphan",
                    message=f"Route '{route_path}' is not referenced from any template.",
                    route=route_path,
                ))

    return result


def _load_template_sources(kida_env: Any) -> dict[str, str]:
    """Load all template sources from the kida environment's loader.

    Returns a dict of template_name → source_text.

    """
    sources: dict[str, str] = {}
    loader = kida_env.loader
    if loader is None:
        return sources

    # FileSystemLoader has list_templates()
    list_fn = getattr(loader, "list_templates", None)
    if list_fn is not None:
        try:
            names = list_fn()
            for name in names:
                try:
                    source, _ = loader.get_source(name)
                    sources[name] = source
                except Exception:
                    pass
        except Exception:
            pass

    return sources


# ---------------------------------------------------------------------------
# Decorator for attaching contracts to handlers
# ---------------------------------------------------------------------------


def contract(
    returns: FragmentContract | SSEContract | None = None,
    *,
    description: str = "",
) -> Any:
    """Attach a contract to a route handler.

    Usage::

        @app.route("/search", methods=["POST"])
        @contract(returns=FragmentContract("search.html", "results"))
        async def search(request):
            ...

    """
    rc = RouteContract(returns=returns, description=description)

    def decorator(func: Any) -> Any:
        func._chirp_contract = rc
        return func

    return decorator
