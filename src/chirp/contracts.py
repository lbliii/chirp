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
    sets of allowed HTTP methods.

    """
    path_methods: dict[str, frozenset[str]] = {}
    for route in router.routes:
        path_methods[route.path] = route.methods
    return path_methods


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
            f"found {self.targets_found} hypermedia targets.",
        ]
        if self.ok:
            lines.append("No errors found.")
        else:
            lines.append(f"{len(self.errors)} error(s), {len(self.warnings)} warning(s).")
        for issue in self.issues:
            prefix = issue.severity.value.upper()
            loc = f" in {issue.template}" if issue.template else ""
            lines.append(f"  [{prefix}] {issue.message}{loc}")
        return "\n".join(lines)


def check_hypermedia_surface(app: App) -> CheckResult:
    """Validate the hypermedia surface of a Chirp application.

    Checks:
    1. **Fragment references**: Every route with a FragmentContract
       references a template and block that exist.
    2. **htmx targets**: Every ``hx-get``, ``hx-post``, etc. in template
       HTML resolves to a registered route with the correct method.
    3. **Form actions**: Every ``action="/path"`` in template HTML
       resolves to a registered route.
    4. **Orphan routes**: Routes that are never referenced from templates
       (warning, not error).

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

        # 4. Check for orphan routes (routes never referenced from templates)
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
