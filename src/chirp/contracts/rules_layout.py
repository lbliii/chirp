"""Layout chain checks for page-convention templates."""

import re
from typing import Any

from chirp.templating.fragment_target_registry import FragmentTargetRegistry

from .patterns import ID_ATTR as _ID_ATTR_RE
from .types import ContractIssue, Severity

_EXTENDS_TAG = re.compile(r"\{%\s*extends\s+")
_EXTENDS_LITERAL = re.compile(r"\{%\s*extends\s+([\"'])(?P<template>[^\"']+)\1")
_HX_TARGET_ATTR = re.compile(r"\bhx-target\s*=\s*([\"'])(?P<target>.*?)\1", re.IGNORECASE)
_HX_SELECT_ATTR = re.compile(r"\bhx-select\s*=\s*([\"'])(?P<select>.*?)\1", re.IGNORECASE)
_SIMPLE_ID_SELECTOR = re.compile(r"^#(?P<id>[A-Za-z][\w:.-]*)$")


def _all_dom_ids(template_sources: dict[str, str]) -> frozenset[str]:
    """Collect every ``id="..."`` value across all template sources."""
    ids: set[str] = set()
    for source in template_sources.values():
        ids.update(_ID_ATTR_RE.findall(source))
    return frozenset(ids)


def _template_source_chain(
    template_name: str,
    template_sources: dict[str, str],
) -> tuple[tuple[str, str], ...]:
    """Return a literal ``extends`` chain, child first, without cycles."""
    chain: list[tuple[str, str]] = []
    seen: set[str] = set()
    current = template_name
    while current not in seen:
        seen.add(current)
        source = template_sources.get(current)
        if source is None:
            break
        chain.append((current, source))
        match = _EXTENDS_LITERAL.search(source)
        if match is None:
            break
        current = match.group("template")
    return tuple(chain)


def _effective_hx_target_select(
    template_name: str,
    template_sources: dict[str, str],
) -> tuple[str, str, str] | None:
    """Find the first literal target/select pair in a layout inheritance chain."""
    for source_name, source in _template_source_chain(template_name, template_sources):
        hx_target = _HX_TARGET_ATTR.search(source)
        hx_select = _HX_SELECT_ATTR.search(source)
        if hx_target is not None and hx_select is not None:
            return (
                source_name,
                hx_target.group("target").strip(),
                hx_select.group("select").strip(),
            )
    return None


def _template_chain_has_id(
    template_name: str,
    element_id: str,
    template_sources: dict[str, str],
) -> bool:
    return any(
        element_id in _ID_ATTR_RE.findall(source)
        for _, source in _template_source_chain(template_name, template_sources)
    )


def _check_omitted_outlet_selections(
    discovered_routes: list[Any],
    template_sources: dict[str, str],
    fragment_target_registry: FragmentTargetRegistry | None,
) -> list[ContractIssue]:
    """Error when an omitted outlet owns an hx-select absent from page HTML."""
    if fragment_target_registry is None:
        return []
    issues: list[ContractIssue] = []
    seen: set[tuple[str, str, str, str]] = set()
    for route in discovered_routes:
        page_template = getattr(route, "template_name", None)
        chain = getattr(route, "layout_chain", None)
        route_path = getattr(route, "url_path", None)
        if not page_template or chain is None or not route_path:
            continue
        for layout in getattr(chain, "layouts", ()):
            outlet = getattr(layout, "outlet_target_id", None)
            if not outlet:
                continue
            config = fragment_target_registry.get(outlet)
            if config is None:
                continue
            skips_layout = (
                getattr(layout, "outlet_mode", "compose") == "replace" or config.omit_outer_layouts
            )
            if not skips_layout:
                continue
            selection = _effective_hx_target_select(layout.template_name, template_sources)
            if selection is None:
                continue
            selector_template, hx_target, hx_select = selection
            if hx_target.lstrip("#") != outlet.lstrip("#"):
                continue
            selector_match = _SIMPLE_ID_SELECTOR.fullmatch(hx_select)
            if selector_match is None:
                continue
            selector_id = selector_match.group("id")
            if _template_chain_has_id(page_template, selector_id, template_sources):
                continue
            identity = (route_path, page_template, outlet, hx_select)
            if identity in seen:
                continue
            seen.add(identity)
            mode = (
                "outlet_mode='replace'"
                if getattr(layout, "outlet_mode", "compose") == "replace"
                else "omit_outer_layouts=True"
            )
            issues.append(
                ContractIssue(
                    severity=Severity.ERROR,
                    category="layout_outlet",
                    message=(
                        f"Route '{route_path}' renders fragment block "
                        f"'{config.fragment_block}' into #{outlet}, but layout "
                        f"'{layout.template_name}' uses {mode} and inherits "
                        f"hx-select=\"{hx_select}\" from '{selector_template}'. "
                        f"Page template '{page_template}' does not define "
                        f'id="{selector_id}", so htmx would empty #{outlet}.'
                    ),
                    route=route_path,
                    template=page_template,
                    details=(
                        f"Use outlet_mode='compose', include {hx_select} in the rendered "
                        f"'{config.fragment_block}' surface, or remove the inherited hx-select. "
                        "Chirp emits HX-Reselect: * as a runtime corruption backstop."
                    ),
                )
            )
    return issues


def check_layout_chains(
    layout_chains: list[Any],
    template_sources: dict[str, str],
    fragment_target_registry: FragmentTargetRegistry | None = None,
    discovered_routes: list[Any] | None = None,
) -> list[ContractIssue]:
    """Validate layout chains: targets, scopes, outlets, frames, extends conflict."""
    issues: list[ContractIssue] = []
    seen_chains: set[tuple[tuple[str, str, int, str | None], ...]] = set()
    dom_ids: frozenset[str] | None = None

    for chain in layout_chains:
        layouts = getattr(chain, "layouts", ())
        if not layouts:
            continue
        signature = tuple(
            (
                layout.template_name,
                layout.target,
                layout.depth,
                getattr(layout, "swap_scope_name", None),
            )
            for layout in layouts
        )
        if signature in seen_chains:
            continue
        seen_chains.add(signature)

        targets_seen: dict[str, str] = {}
        for layout in layouts:
            target = layout.target
            if target in targets_seen:
                issues.append(
                    ContractIssue(
                        severity=Severity.WARNING,
                        category="layout_chain",
                        message=(
                            f"Duplicate target '{target}' in layout chain: "
                            f"{targets_seen[target]} and {layout.template_name}. "
                            "find_start_index_for_target returns first match."
                        ),
                        template=layout.template_name,
                    )
                )
            else:
                targets_seen[target] = layout.template_name

        scopes_seen: dict[str, str] = {}
        for layout in layouts:
            scope = getattr(layout, "swap_scope_name", None)
            if not scope:
                continue
            if scope in scopes_seen:
                issues.append(
                    ContractIssue(
                        severity=Severity.WARNING,
                        category="layout_chain",
                        message=(
                            f"Duplicate swap_scope '{scope}' in layout chain: "
                            f"{scopes_seen[scope]} and {layout.template_name}."
                        ),
                        template=layout.template_name,
                    )
                )
            else:
                scopes_seen[scope] = layout.template_name

        # --- outlet_target_id: declared outlet must exist in some template ---
        for layout in layouts:
            outlet = getattr(layout, "outlet_target_id", None)
            if not outlet:
                continue
            if dom_ids is None:
                dom_ids = _all_dom_ids(template_sources)
            if outlet not in dom_ids:
                issues.append(
                    ContractIssue(
                        severity=Severity.WARNING,
                        category="layout_outlet",
                        message=(
                            f"Layout {layout.template_name} declares "
                            f"outlet_target_id '{outlet}' but no template "
                            f'contains id="{outlet}". The outlet may be '
                            "rendered by a macro or component at runtime."
                        ),
                        template=layout.template_name,
                    )
                )

        # --- outlet_target_id: must be registered as a fragment target ---
        if fragment_target_registry is not None:
            registered = fragment_target_registry.registered_targets
            for layout in layouts:
                outlet = getattr(layout, "outlet_target_id", None)
                if not outlet:
                    continue
                if outlet not in registered:
                    issues.append(
                        ContractIssue(
                            severity=Severity.WARNING,
                            category="layout_outlet",
                            message=(
                                f"Layout {layout.template_name} declares outlet "
                                f"'{outlet}' but it is not registered as a fragment "
                                f"target. Boosted navigation targeting #{outlet} will "
                                f"get a full-page response instead of a fragment. Call "
                                f"app.register_fragment_target('{outlet}', "
                                f"fragment_block=...) or register it via a "
                                f"PageShellContract."
                            ),
                            template=layout.template_name,
                        )
                    )

        # --- frame_targets: must not be registered as swappable targets ---
        if fragment_target_registry is not None:
            registered = fragment_target_registry.registered_targets
            for layout in layouts:
                frames = getattr(layout, "frame_targets", None)
                if not frames:
                    continue
                swappable = frames & registered
                issues.extend(
                    ContractIssue(
                        severity=Severity.WARNING,
                        category="layout_frame",
                        message=(
                            f"Layout {layout.template_name} declares "
                            f"'{fid}' as a frame target (immutable), but "
                            "it is registered as a fragment swap target. "
                            "Frame targets should not be swappable."
                        ),
                        template=layout.template_name,
                    )
                    for fid in sorted(swappable)
                )

        # --- conflicting outlet_target_id within the same chain ---
        outlets_by_depth: dict[int, tuple[str, str]] = {}
        for layout in layouts:
            outlet = getattr(layout, "outlet_target_id", None)
            if not outlet:
                continue
            depth = layout.depth
            if depth in outlets_by_depth:
                prev_outlet, prev_tmpl = outlets_by_depth[depth]
                if prev_outlet != outlet:
                    issues.append(
                        ContractIssue(
                            severity=Severity.WARNING,
                            category="layout_outlet",
                            message=(
                                f"Conflicting outlet_target_id at depth {depth}: "
                                f"'{prev_outlet}' ({prev_tmpl}) vs "
                                f"'{outlet}' ({layout.template_name})."
                            ),
                            template=layout.template_name,
                        )
                    )
            else:
                outlets_by_depth[depth] = (outlet, layout.template_name)

        issues.extend(
            ContractIssue(
                severity=Severity.WARNING,
                category="layout_chain",
                message=(
                    f"Inner layout {layout.template_name} defaulting to "
                    "target 'body'. Add {# target: element_id #}."
                ),
                template=layout.template_name,
            )
            for layout in layouts
            if layout.depth > 0 and layout.target == "body"
        )

        for layout in layouts:
            source = template_sources.get(layout.template_name)
            if source is None:
                continue
            if not getattr(layout, "outlet_target_id", None) and "hx-boost" in source.lower():
                hx_target = _HX_TARGET_ATTR.search(source)
                hx_select = _HX_SELECT_ATTR.search(source)
                if hx_target and hx_select:
                    target = hx_target.group("target").strip().lstrip("#")
                    select = hx_select.group("select").strip()
                    if target and target != layout.target:
                        issues.append(
                            ContractIssue(
                                severity=Severity.WARNING,
                                category="layout_outlet",
                                message=(
                                    f"Layout {layout.template_name} targets #{target} with "
                                    f'hx-select="{select}" but does not declare an outlet. '
                                    f"Boosted navigation can render a response without "
                                    f"{select}, causing htmx to empty #{target}. Add "
                                    f"{{# outlet: {target} #}} to the layout."
                                ),
                                template=layout.template_name,
                            )
                        )
            if layout.depth > 0 and _EXTENDS_TAG.search(source):
                issues.append(
                    ContractIssue(
                        severity=Severity.WARNING,
                        category="layout_chain",
                        message=(
                            f"Inner layout {layout.template_name} uses "
                            "{% extends %}. With render_with_blocks, the child may wipe the shell."
                        ),
                        template=layout.template_name,
                    )
                )
            if "hx-disinherit" in source.lower():
                issues.append(
                    ContractIssue(
                        severity=Severity.INFO,
                        category="layout_chain",
                        message=(
                            f"Layout {layout.template_name} uses hx-disinherit. "
                            "If hx-disinherit is protecting against inherited hx-select "
                            "or hx-target from a broad container, the underlying cause is "
                            "likely a layout mismatch. Fragment-returning routes should use "
                            "shell.html (no global hx-select) rather than boost.html."
                        ),
                        template=layout.template_name,
                    )
                )
    issues.extend(
        _check_omitted_outlet_selections(
            discovered_routes or [],
            template_sources,
            fragment_target_registry,
        )
    )
    return issues
