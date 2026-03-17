"""Route directory contract validation."""

import inspect
from collections import defaultdict
from typing import Any

from kida import Environment

from chirp.pages.types import RouteMeta, Section, TabItem
from chirp.templating.fragment_target_registry import FragmentTargetRegistry

from .types import ContractIssue, Severity


def check_section_bindings(
    route_metas: dict[str, RouteMeta | None],
    sections: dict[str, Section],
) -> list[ContractIssue]:
    """Warn if RouteMeta.section references unknown section."""
    issues: list[ContractIssue] = []
    for path, meta in route_metas.items():
        if meta is None or meta.section is None:
            continue
        if meta.section not in sections:
            issues.append(
                ContractIssue(
                    severity=Severity.WARNING,
                    category="route_contract",
                    message=(
                        f"Route '{path}' references unknown section '{meta.section}'. "
                        "Register the section with app.register_section() before mount_pages()."
                    ),
                    route=path,
                )
            )
    return issues


def check_shell_mode_blocks(
    route_metas: dict[str, RouteMeta | None],
    route_templates: dict[str, str],
    fragment_target_registry: FragmentTargetRegistry,
    kida_env: Environment | None,
) -> list[ContractIssue]:
    """Error if shell_mode='tabbed' but template lacks required blocks."""
    issues: list[ContractIssue] = []
    if kida_env is None:
        return issues
    required = fragment_target_registry.required_fragment_blocks
    if not required:
        return issues

    for path, meta in route_metas.items():
        if meta is None or meta.shell_mode != "tabbed":
            continue
        template_name = route_templates.get(path)
        if not template_name:
            continue
        try:
            template = kida_env.get_template(template_name)
            blocks = template.block_metadata()
        except Exception:
            continue
        missing = [b for b in required if b not in blocks]
        if missing:
            issues.append(
                ContractIssue(
                    severity=Severity.ERROR,
                    category="route_contract",
                    message=(
                        f"Route '{path}' has shell_mode='tabbed' but template "
                        f"'{template_name}' lacks required block(s): {', '.join(missing)}."
                    ),
                    route=path,
                    template=template_name,
                )
            )
    return issues


def check_route_file_consistency(
    route_metas: dict[str, RouteMeta | None],
    page_route_paths: set[str],
    action_route_paths: set[str] | None = None,
) -> list[ContractIssue]:
    """Info-level for page routes without _meta.py.

    Action routes (no sibling template, pure mutation handlers) are skipped
    because they render fragments rather than standalone pages and don't
    benefit from title/breadcrumb metadata.
    """
    skip = action_route_paths or set()
    return [
        ContractIssue(
            severity=Severity.INFO,
            category="route_contract",
            message=(
                f"Route '{path}' has no _meta.py. Consider adding one for "
                "title, section, breadcrumb_label, etc."
            ),
            route=path,
        )
        for path in page_route_paths
        if path not in skip and (path not in route_metas or route_metas[path] is None)
    ]


def check_duplicate_routes(discovered_routes: list[Any]) -> list[ContractIssue]:
    """Warn if two routes resolve to the same (url_path, method) pair."""
    issues: list[ContractIssue] = []
    seen: dict[tuple[str, str], list[str]] = defaultdict(list)
    for route in discovered_routes:
        path = getattr(route, "url_path", "")
        for method in getattr(route, "methods", ()):
            key = (path, method)
            seen[key].append(path)
    for (path, method), paths in seen.items():
        if len(paths) > 1:
            issues.append(
                ContractIssue(
                    severity=Severity.WARNING,
                    category="route_contract",
                    message=(
                        f"Duplicate route: '{path}' with method {method} "
                        f"registered {len(paths)} times."
                    ),
                    route=path,
                )
            )
    return issues


def check_section_tab_hrefs(
    sections: dict[str, Section],
    page_route_paths: set[str],
) -> list[ContractIssue]:
    """Warn if a TabItem.href does not match any registered route path."""
    issues: list[ContractIssue] = []
    for section_id, section in sections.items():
        for tab in getattr(section, "tab_items", ()):
            if not isinstance(tab, TabItem):
                continue
            href = getattr(tab, "href", "") or ""
            path = href.split("?")[0].rstrip("/") or "/"
            if path not in page_route_paths:
                issues.append(
                    ContractIssue(
                        severity=Severity.WARNING,
                        category="route_contract",
                        message=(
                            f"Section '{section_id}' tab href '{href}' "
                            "does not match any registered route path."
                        ),
                        route=path,
                    )
                )
    return issues


def check_context_provider_signatures(
    discovered_routes: list[Any],
    providers: dict[type, Any] | None,
) -> list[ContractIssue]:
    """Warn if _context.py param matches neither path param nor provider type."""
    issues: list[ContractIssue] = []
    provider_types = set(providers.keys()) if providers else set()
    known_names = {"request", "context", "cascade_ctx"}
    for route in discovered_routes:
        path_params: set[str] = set()
        url_path = getattr(route, "url_path", "")
        if "{" in url_path:
            import re

            for m in re.finditer(r"\{(\w+)\}", url_path):
                path_params.add(m.group(1))
        # Nested routes inherit parent context; params like projects/project come from cascade
        providers_list = getattr(route, "context_providers", ())
        if len(providers_list) > 1:
            continue
        allowed = path_params | known_names
        for p in providers_list:
            func = getattr(p, "func", None)
            if func is None:
                continue
            try:
                sig = inspect.signature(func, eval_str=True)
            except Exception:
                continue
            for name, param in sig.parameters.items():
                if name in allowed:
                    continue
                if (
                    param.annotation is not inspect.Parameter.empty
                    and param.annotation in provider_types
                ):
                    continue
                issues.append(
                    ContractIssue(
                        severity=Severity.INFO,
                        category="route_contract",
                        message=(
                            f"Route '{url_path}' context provider param '{name}' "
                            "is not a path param or provider type (may come from parent)."
                        ),
                        route=url_path,
                    )
                )
    return issues
