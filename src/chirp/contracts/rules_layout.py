"""Layout chain checks for page-convention templates."""

import re
from typing import Any

from chirp.templating.fragment_target_registry import FragmentTargetRegistry

from .patterns import ID_ATTR as _ID_ATTR_RE
from .types import ContractIssue, Severity

_EXTENDS_TAG = re.compile(r"\{%\s*extends\s+")


def _all_dom_ids(template_sources: dict[str, str]) -> frozenset[str]:
    """Collect every ``id="..."`` value across all template sources."""
    ids: set[str] = set()
    for source in template_sources.values():
        ids.update(_ID_ATTR_RE.findall(source))
    return frozenset(ids)


def check_layout_chains(
    layout_chains: list[Any],
    template_sources: dict[str, str],
    fragment_target_registry: FragmentTargetRegistry | None = None,
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
    return issues
