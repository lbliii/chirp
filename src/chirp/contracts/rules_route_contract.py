"""Route directory contract validation."""

import inspect
from collections import defaultdict
from typing import Any

from kida import Environment

from chirp.pages.types import RouteMeta, Section, TabItem
from chirp.templating.fragment_target_registry import FragmentTargetRegistry

from .types import ContractIssue, Severity


def _normalize_href_path(href: str) -> str:
    return href.split("?")[0].rstrip("/") or "/"


def _tab_href_matches_page_routes(
    tab_path: str,
    match_mode: str,
    page_route_paths: set[str],
) -> bool:
    """True if *tab_path* is exact or, for prefix tabs, covered by a registered route."""
    if tab_path in page_route_paths:
        return True
    if match_mode != "prefix":
        return False
    if tab_path == "/":
        return bool(page_route_paths)
    prefixes = (tab_path + "/", tab_path + "{")
    return any(route.startswith(prefixes) for route in page_route_paths)


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
    meta_provider_paths: set[str] | None = None,
) -> list[ContractIssue]:
    """Info-level for page routes without _meta.py.

    Action routes (no sibling template, pure mutation handlers) are skipped
    because they render fragments rather than standalone pages and don't
    benefit from title/breadcrumb metadata.

    Routes whose ``_meta.py`` defines ``meta()`` (dynamic metadata) register a
    meta provider at discovery time with static ``meta`` left ``None``; those
    paths are listed in *meta_provider_paths* and are treated as having metadata.
    """
    skip_action = action_route_paths or set()
    skip_meta_provider = meta_provider_paths or set()
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
        if path not in skip_action
        and path not in skip_meta_provider
        and (path not in route_metas or route_metas[path] is None)
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
    """Warn if a TabItem.href does not match any registered route path.

    For prefix-match tabs, the href may be a parent path; at least one
    registered route must equal it or lie under it (including ``/seg/{param}``).

    Emits a warning when two tabs in the same section normalize to the same href.
    """
    issues: list[ContractIssue] = []
    for section_id, section in sections.items():
        seen_hrefs: set[str] = set()
        for tab in getattr(section, "tab_items", ()):
            if not isinstance(tab, TabItem):
                continue
            href = getattr(tab, "href", "") or ""
            path = _normalize_href_path(href)
            match_mode = getattr(tab, "match", "exact") or "exact"
            if path in seen_hrefs:
                issues.append(
                    ContractIssue(
                        severity=Severity.WARNING,
                        category="route_contract",
                        message=(
                            f"Section '{section_id}' has duplicate tab href '{href}' "
                            f"(normalized path '{path}')."
                        ),
                        route=path,
                    )
                )
            seen_hrefs.add(path)
            if _tab_href_matches_page_routes(path, match_mode, page_route_paths):
                continue
            issues.append(
                ContractIssue(
                    severity=Severity.WARNING,
                    category="route_contract",
                    message=(
                        f"Section '{section_id}' tab href '{href}' "
                        "(match="
                        f"'{match_mode}') does not match any registered route path."
                    ),
                    route=path,
                )
            )
    return issues


def check_section_coverage(
    route_metas: dict[str, RouteMeta | None],
    sections: dict[str, Section],
    page_route_paths: set[str],
    meta_provider_paths: set[str] | None = None,
) -> list[ContractIssue]:
    """Info when routes sit under a section prefix but lack ``meta.section``.

    Routes whose ``_meta.py`` defines ``meta()`` (dynamic metadata) register a
    meta provider at discovery time with static ``meta`` left ``None``; those
    paths are listed in *meta_provider_paths* and are excluded from the
    "no meta.section" INFO to avoid false positives.

    Warn when ``meta.section`` is set but the route path is not covered by that
    section's ``active_prefixes`` (when prefixes are defined).
    """
    issues: list[ContractIssue] = []
    skip_meta_provider = meta_provider_paths or set()
    for path in page_route_paths:
        meta = route_metas.get(path)
        covering = [s for s in sections.values() if s.is_active(path)]
        if (
            covering
            and (meta is None or meta.section is None)
            and path not in skip_meta_provider
        ):
            issues.append(
                ContractIssue(
                    severity=Severity.INFO,
                    category="route_contract",
                    message=(
                        f"Route '{path}' is under a section's active_prefixes but "
                        "has no meta.section; set section in _meta.py for consistent "
                        "shell context (tabs, breadcrumbs)."
                    ),
                    route=path,
                )
            )
        elif meta and meta.section:
            section = sections.get(meta.section)
            if section is not None and section.active_prefixes and not section.is_active(path):
                issues.append(
                    ContractIssue(
                        severity=Severity.WARNING,
                        category="route_contract",
                        message=(
                            f"Route '{path}' has meta.section='{meta.section}' but that "
                            "section's active_prefixes do not cover this path."
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
