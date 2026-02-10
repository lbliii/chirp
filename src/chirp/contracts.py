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

import dataclasses
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

    Used for documentation and validation.  Optionally declares
    fragments that the SSE stream yields, so ``app.check()`` can
    verify the templates/blocks exist.

    """

    event_types: frozenset[str] = frozenset()
    fragments: tuple[FragmentContract, ...] = ()


@dataclass(frozen=True, slots=True)
class FormContract:
    """Declares which dataclass a route binds form data to.

    Used by ``app.check()`` to verify that ``<input name="...">``,
    ``<select name="...">``, and ``<textarea name="...">`` fields in the
    template match the dataclass fields expected by the handler.

    """

    datacls: type
    template: str
    block: str | None = None


@dataclass(frozen=True, slots=True)
class RouteContract:
    """Full contract metadata for a route.

    Attached to routes via the ``contract`` parameter on ``@app.route()``.

    """

    returns: FragmentContract | SSEContract | None = None
    form: FormContract | None = None
    description: str = ""


# ---------------------------------------------------------------------------
# Template scanner — extract htmx targets from template AST
# ---------------------------------------------------------------------------

# htmx attributes that reference server URLs
_HTMX_URL_ATTRS = frozenset({
    "hx-get", "hx-post", "hx-put", "hx-patch", "hx-delete",
})

# All valid htmx attributes (from https://htmx.org/reference/)
_HTMX_ALL_ATTRS = frozenset({
    # Core HTTP
    "hx-get", "hx-post", "hx-put", "hx-patch", "hx-delete",
    # Triggering
    "hx-trigger",
    # Targeting & swapping
    "hx-target", "hx-swap", "hx-swap-oob", "hx-select", "hx-select-oob",
    # URL management
    "hx-push-url", "hx-replace-url",
    # Parameters & values
    "hx-vals", "hx-headers", "hx-include", "hx-params", "hx-encoding",
    # Progressive enhancement
    "hx-boost",
    # Loading UX
    "hx-indicator", "hx-disabled-elt",
    # Synchronization
    "hx-sync",
    # Validation
    "hx-validate",
    # Confirmation
    "hx-confirm", "hx-prompt",
    # Preservation
    "hx-preserve",
    # Extensions
    "hx-ext",
    # Inheritance control
    "hx-disinherit", "hx-inherit",
    # History
    "hx-history", "hx-history-elt",
    # Misc
    "hx-request", "hx-disable",
})
# Note: hx-on::* (event handlers) use a wildcard prefix pattern, checked separately

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


# ---------------------------------------------------------------------------
# Template reference scanner — extract extends/include/from/import
# ---------------------------------------------------------------------------

# Regex: {% extends "..." %}, {% include "..." %}, {% from "..." import ... %},
#        {% import "..." as ... %}
_TEMPLATE_REF_PATTERN = re.compile(
    r"""\{%-?\s*(?:extends|include|from|import)\s+["']([^"']+)["']""",
)


def _extract_template_references(source: str) -> set[str]:
    """Extract template names referenced via Jinja tags.

    Catches static references from ``{% extends %}``, ``{% include %}``,
    ``{% from %}``, and ``{% import %}``.  Dynamic expressions
    (e.g. ``{% include variable %}``) are not captured.
    """
    return {m.group(1) for m in _TEMPLATE_REF_PATTERN.finditer(source)}


# ---------------------------------------------------------------------------
# Form field scanner — extract <input>, <select>, <textarea> name attributes
# ---------------------------------------------------------------------------

# Regex: <input name="...">, <select name="...">, <textarea name="...">
_FORM_FIELD_PATTERN = re.compile(
    r"<(?:input|select|textarea)\b[^>]*?\bname\s*=\s*[\"']([^\"']+)[\"']",
    re.IGNORECASE,
)

# Field names to exclude from form validation (framework-injected, not user data)
_FORM_EXCLUDED_FIELDS = frozenset({
    "_csrf_token", "csrf_token", "_method",
})


def _extract_form_field_names(source: str) -> set[str]:
    """Extract ``name`` attribute values from form fields in template HTML.

    Scans for ``<input>``, ``<select>``, and ``<textarea>`` elements.
    Skips template expressions and framework-injected fields like
    CSRF tokens.
    """
    names: set[str] = set()
    for match in _FORM_FIELD_PATTERN.finditer(source):
        name = match.group(1).strip()
        if not name or "{{" in name or "{%" in name:
            continue
        if name in _FORM_EXCLUDED_FIELDS:
            continue
        names.add(name)
    return names


def _closest_field(target: str, fields: set[str], *, max_dist: int = 2) -> str | None:
    """Find the closest field name by edit distance, or ``None``."""
    if not fields:
        return None
    best: str | None = None
    best_dist = max_dist + 1
    for candidate in sorted(fields):  # sorted for determinism
        dist = _edit_distance(target, candidate)
        if dist < best_dist:
            best_dist = dist
            best = candidate
    return best if best_dist <= max_dist else None


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
# hx-indicator selector scanner
# ---------------------------------------------------------------------------

# Regex: hx-indicator="..." values (CSS selectors)
_HX_INDICATOR_PATTERN = re.compile(
    r'hx-indicator\s*=\s*["\']([^"\']*)["\']',
)


def _check_hx_indicator_selectors(
    template_sources: dict[str, str],
    all_ids: set[str],
) -> list[ContractIssue]:
    """Validate ``hx-indicator`` selectors against the pool of static element IDs.

    Only validates simple ``#id`` selectors.  Extended selectors (``closest``,
    ``find``, ``inherit``) and comma-separated multiples are skipped.
    """
    issues: list[ContractIssue] = []

    for tmpl_name, source in template_sources.items():
        for match in _HX_INDICATOR_PATTERN.finditer(source):
            value = match.group(1).strip()
            if not value or "{{" in value or "{%" in value:
                continue
            # Skip extended/special selectors
            first_word = value.split()[0] if value else ""
            if first_word.lower() in {"closest", "find", "inherit"}:
                continue
            # Skip comma-separated multiples
            if "," in value:
                continue
            # Validate #id selectors
            if value.startswith("#"):
                if " " in value:
                    continue
                target_id = value[1:]
                if not target_id:
                    continue
                if target_id not in all_ids:
                    suggestion = _closest_id(target_id, all_ids)
                    hint = f' Did you mean "#{suggestion}"?' if suggestion else ""
                    issues.append(ContractIssue(
                        severity=Severity.WARNING,
                        category="hx-indicator",
                        message=(
                            f'hx-indicator="#{target_id}" — no element with '
                            f'id="{target_id}" found in any template.{hint}'
                        ),
                        template=tmpl_name,
                    ))

    return issues


# ---------------------------------------------------------------------------
# hx-boost value scanner
# ---------------------------------------------------------------------------

_HX_BOOST_PATTERN = re.compile(r'hx-boost\s*=\s*["\']([^"\']*)["\']')


def _check_hx_boost(
    template_sources: dict[str, str],
) -> list[ContractIssue]:
    """Validate ``hx-boost`` values are ``"true"`` or ``"false"``.

    htmx silently treats any non-``"true"`` value as false, which is
    confusing.  Chirp catches this at compile time.
    """
    issues: list[ContractIssue] = []
    for tmpl_name, source in template_sources.items():
        for match in _HX_BOOST_PATTERN.finditer(source):
            value = match.group(1).strip().lower()
            # Skip template expressions
            if "{{" in value or "{%" in value:
                continue
            if value not in ("true", "false"):
                issues.append(ContractIssue(
                    severity=Severity.WARNING,
                    category="hx-boost",
                    message=(
                        f'hx-boost="{match.group(1)}" — '
                        f'must be "true" or "false".'
                    ),
                    template=tmpl_name,
                ))
    return issues


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
    dead_templates_found: int = 0
    sse_fragments_validated: int = 0
    forms_validated: int = 0
    component_calls_validated: int = 0
    page_context_warnings: int = 0

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
        # Optional counters — only include when non-zero
        extras: list[str] = []
        if self.dead_templates_found:
            extras.append(f"{self.dead_templates_found} dead template(s)")
        if self.sse_fragments_validated:
            extras.append(f"{self.sse_fragments_validated} SSE fragment(s) validated")
        if self.forms_validated:
            extras.append(f"{self.forms_validated} form(s) validated")
        if self.component_calls_validated:
            extras.append(
                f"{self.component_calls_validated} component call(s) validated"
            )
        if self.page_context_warnings:
            extras.append(
                f"{self.page_context_warnings} Page context warning(s)"
            )
        if extras:
            lines.append(", ".join(extras) + ".")

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
    2. **SSE fragment references**: SSEContract fragments resolve to
       valid templates and blocks.
    3. **htmx URL targets**: Every ``hx-get``, ``hx-post``, etc. in
       template HTML resolves to a registered route with the correct method.
    4. **hx-target selectors**: Every ``hx-target="#id"`` in template HTML
       references an element ID that exists somewhere in the template tree
       (warning — IDs may come from dynamic expressions or JS).
    5. **Accessibility**: htmx URL attributes on non-interactive elements
       (``<div>``, ``<span>``, etc.) without ``role`` or ``tabindex``
       (warning, not error).
    6. **Form field validation**: Routes with FormContract have template
       fields that match the dataclass fields.
    7. **Orphan routes**: Routes that are never referenced from templates
       (info, not error).
    8. **Dead templates**: Templates not referenced by any route or other
       template (info, not error).
    9. **Page context gaps**: Routes with FragmentContract where the full
       template requires variables the target block does not — a sign
       that full-page Page renders may crash at runtime (warning).
    10. **Component call validation**: ``{% call %}`` sites match
        ``{% def %}`` signatures (requires kida typed def support).

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
                    # block_metadata() returns {name: BlockMetadata}
                    blocks = tmpl.block_metadata()
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

        # 2a. Check SSE fragment contracts
        elif isinstance(contract.returns, SSEContract) and kida_env is not None:
            for fc in contract.returns.fragments:
                result.sse_fragments_validated += 1
                try:
                    tmpl = kida_env.get_template(fc.template)
                    blocks = tmpl.block_metadata()
                    if fc.block not in blocks:
                        result.issues.append(ContractIssue(
                            severity=Severity.ERROR,
                            category="sse",
                            message=(
                                f"SSE route '{route.path}' yields Fragment "
                                f"'{fc.template}':'{fc.block}' but block "
                                f"doesn't exist."
                            ),
                            route=route.path,
                            template=fc.template,
                        ))
                except Exception:
                    result.issues.append(ContractIssue(
                        severity=Severity.ERROR,
                        category="sse",
                        message=(
                            f"SSE route '{route.path}' yields Fragment "
                            f"'{fc.template}' which could not be loaded."
                        ),
                        route=route.path,
                        template=fc.template,
                    ))

    # 2b. Warn about routes with InlineTemplate return annotations
    _check_inline_templates(router, result)

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

        # 4b. Check hx-indicator selectors against static element IDs
        result.issues.extend(_check_hx_indicator_selectors(template_sources, all_ids))

        # 4c. Check hx-boost values
        result.issues.extend(_check_hx_boost(template_sources))

        # 5. Check accessibility — htmx on non-interactive elements
        for tmpl_name, source in template_sources.items():
            a11y_issues = _check_accessibility(source, tmpl_name)
            result.issues.extend(a11y_issues)

        # 6. Form field validation — compare dataclass fields against HTML
        for route in router.routes:
            rc = getattr(route.handler, "_chirp_contract", None)
            if rc is None or rc.form is None:
                continue
            fc = rc.form
            result.forms_validated += 1

            # Load the template (or block) source
            tmpl_source = template_sources.get(fc.template)
            if tmpl_source is None:
                result.issues.append(ContractIssue(
                    severity=Severity.ERROR,
                    category="form",
                    message=(
                        f"Route '{route.path}' FormContract references "
                        f"template '{fc.template}' which is not found."
                    ),
                    route=route.path,
                    template=fc.template,
                ))
                continue

            # If block is specified, try to narrow to block source
            if fc.block is not None:
                block_match = re.search(
                    rf"\{{% block {re.escape(fc.block)} %\}}(.*?)"
                    rf"\{{% endblock",
                    tmpl_source,
                    re.DOTALL,
                )
                if block_match:
                    tmpl_source = block_match.group(1)

            html_fields = _extract_form_field_names(tmpl_source)
            try:
                dc_fields = {f.name for f in dataclasses.fields(fc.datacls)}
            except TypeError:
                result.issues.append(ContractIssue(
                    severity=Severity.WARNING,
                    category="form",
                    message=(
                        f"Route '{route.path}' FormContract datacls "
                        f"'{fc.datacls}' is not a dataclass."
                    ),
                    route=route.path,
                ))
                continue

            # Missing in template = ERROR (form submission will fail)
            for field_name in sorted(dc_fields - html_fields):
                result.issues.append(ContractIssue(
                    severity=Severity.ERROR,
                    category="form",
                    message=(
                        f"Route '{route.path}' (POST) expects field "
                        f"'{field_name}' ({fc.datacls.__name__}.{field_name}) "
                        f"but template '{fc.template}'"
                        + (f" block '{fc.block}'" if fc.block else "")
                        + f" has no <input name=\"{field_name}\">."
                    ),
                    route=route.path,
                    template=fc.template,
                ))

            # Extra in template = WARNING (may be intentional)
            for field_name in sorted(html_fields - dc_fields):
                suggestion = _closest_field(field_name, dc_fields)
                hint = f" Did you mean '{suggestion}'?" if suggestion else ""
                result.issues.append(ContractIssue(
                    severity=Severity.WARNING,
                    category="form",
                    message=(
                        f"Template '{fc.template}'"
                        + (f" block '{fc.block}'" if fc.block else "")
                        + f" has <input name=\"{field_name}\"> which does "
                        f"not match any field in "
                        f"{fc.datacls.__name__}.{hint}"
                    ),
                    template=fc.template,
                    route=route.path,
                ))

        # 7. Orphan routes (routes never referenced from templates).
        #    Page convention routes (from mount_pages()) are accessed via
        #    browser navigation or JavaScript, not htmx attributes — skip them.
        page_route_paths: set[str] = getattr(app, "_page_route_paths", set())
        for route_path in route_paths:
            if route_path in referenced_paths or route_path == "/":
                continue
            if route_path in page_route_paths:
                continue
            result.issues.append(ContractIssue(
                severity=Severity.INFO,
                category="orphan",
                message=f"Route '{route_path}' is not referenced from any template.",
                route=route_path,
            ))

        # 8. Dead template detection — templates never referenced by any
        #    route or other template via extends/include/from/import.
        all_template_names = set(template_sources)
        referenced_templates: set[str] = set()

        # From route FragmentContracts
        for route in router.routes:
            rc = getattr(route.handler, "_chirp_contract", None)
            if rc is None:
                continue
            if isinstance(rc.returns, FragmentContract):
                referenced_templates.add(rc.returns.template)
            elif isinstance(rc.returns, SSEContract):
                for fc in rc.returns.fragments:
                    referenced_templates.add(fc.template)

        # From template source (extends, include, from, import)
        for source in template_sources.values():
            referenced_templates.update(_extract_template_references(source))

        # From page convention (mount_pages) — page.py implicitly renders
        # its sibling page.html, and _layout.html files are wired by the
        # framework's layout chain.
        page_templates: set[str] = getattr(app, "_page_templates", set())
        referenced_templates.update(page_templates)

        dead = sorted(all_template_names - referenced_templates)
        for tmpl_name in dead:
            # Skip partials by convention (leading underscore in filename)
            basename = tmpl_name.rsplit("/", 1)[-1]
            if basename.startswith("_"):
                continue
            # Skip built-in chirp framework templates
            if tmpl_name.startswith("chirp/"):
                continue
            result.dead_templates_found += 1
            result.issues.append(ContractIssue(
                severity=Severity.INFO,
                category="dead",
                message=(
                    f"Template '{tmpl_name}' is not referenced by any "
                    f"route or template."
                ),
                template=tmpl_name,
            ))

    # 9. Page context gap detection — templates whose full-page render
    #    requires variables that the declared fragment block does not use.
    #    This catches bugs where Page("t.html", "block_a", x=1) renders
    #    fine as a fragment but crashes on full-page navigation because
    #    other blocks need variables not passed by the handler.
    if kida_env is not None:
        for route in router.routes:
            rc = getattr(route.handler, "_chirp_contract", None)
            if rc is None or not isinstance(rc.returns, FragmentContract):
                continue
            fc = rc.returns
            try:
                tmpl = kida_env.get_template(fc.template)
                blocks = tmpl.block_metadata()
                if fc.block not in blocks:
                    continue  # Already reported in check 2

                block_deps = blocks[fc.block].depends_on
                full_deps = tmpl.depends_on()

                # Compare top-level variable names
                block_vars = {p.split(".")[0] for p in block_deps}
                full_vars = {p.split(".")[0] for p in full_deps}
                extra = sorted(full_vars - block_vars)

                # Filter out env globals (loop, range, true, false, etc.)
                # by only keeping names that look like user context variables.
                # Kida globals are accessible without being passed, so they're
                # not a concern for missing context.
                env_globals = set(kida_env.globals) if hasattr(kida_env, "globals") else set()
                extra = [v for v in extra if v not in env_globals]

                if extra:
                    result.page_context_warnings += 1
                    result.issues.append(ContractIssue(
                        severity=Severity.WARNING,
                        category="page_context",
                        message=(
                            f"Route '{route.path}' uses block '{fc.block}' "
                            f"but full-page render of '{fc.template}' also "
                            f"needs: {', '.join(extra)}. Pass defaults in "
                            f"your Page() call to avoid runtime errors."
                        ),
                        route=route.path,
                        template=fc.template,
                    ))
            except Exception:
                pass  # Template load errors already reported in check 2

    # 10. Component call validation (requires kida typed def support).
    # Feature-gated: only runs when kida exposes a callable validate_calls().
    if kida_env is not None:
        validate_fn = getattr(kida_env, "validate_calls", None)
        if callable(validate_fn):
            for issue in validate_fn():
                result.component_calls_validated += 1
                result.issues.append(ContractIssue(
                    severity=(
                        Severity.ERROR if issue.is_error else Severity.WARNING
                    ),
                    category="component",
                    message=issue.message,
                    template=getattr(issue, "template", None),
                ))

    return result


def _check_inline_templates(router: Router, result: CheckResult) -> None:
    """Warn about routes whose return annotation includes InlineTemplate.

    InlineTemplate is a prototyping shortcut and should be replaced with
    file-based templates before shipping to production.
    """
    import inspect

    from chirp.templating.returns import InlineTemplate

    for route in router.routes:
        hints = inspect.get_annotations(route.handler, eval_str=False)
        return_hint = hints.get("return")
        if return_hint is None:
            continue

        # Check if return annotation is or contains InlineTemplate
        check_types = (return_hint,)
        origin = getattr(return_hint, "__args__", None)
        if origin is not None:
            check_types = origin  # type: ignore[assignment]

        for t in check_types:
            if t is InlineTemplate or (isinstance(t, type) and issubclass(t, InlineTemplate)):
                result.issues.append(ContractIssue(
                    severity=Severity.WARNING,
                    category="inline_template",
                    message=(
                        f"Route '{route.path}' returns InlineTemplate — "
                        f"replace with a file-based Template before production."
                    ),
                    route=route.path,
                ))
                break


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
    form: FormContract | None = None,
    description: str = "",
) -> Any:
    """Attach a contract to a route handler.

    Usage::

        @app.route("/search", methods=["POST"])
        @contract(returns=FragmentContract("search.html", "results"))
        async def search(request):
            ...

    """
    rc = RouteContract(returns=returns, form=form, description=description)

    def decorator(func: Any) -> Any:
        func._chirp_contract = rc
        return func

    return decorator
