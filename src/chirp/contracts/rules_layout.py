"""Layout chain checks for page-convention templates."""

import re
from typing import Any

from .types import ContractIssue, Severity


def check_layout_chains(
    layout_chains: list[Any],
    template_sources: dict[str, str],
) -> list[ContractIssue]:
    """Validate layout chains: duplicate targets, missing target, extends conflict."""
    issues: list[ContractIssue] = []
    seen_chains: set[tuple[tuple[str, str, int], ...]] = set()
    for chain in layout_chains:
        layouts = getattr(chain, "layouts", ())
        if not layouts:
            continue
        signature = tuple((layout.template_name, layout.target, layout.depth) for layout in layouts)
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

        for layout in layouts:
            if layout.depth > 0 and layout.target == "body":
                issues.append(
                    ContractIssue(
                        severity=Severity.WARNING,
                        category="layout_chain",
                        message=(
                            f"Inner layout {layout.template_name} defaulting to "
                            "target 'body'. Add {# target: element_id #}."
                        ),
                        template=layout.template_name,
                    )
                )

        for layout in layouts:
            source = template_sources.get(layout.template_name)
            if source is None:
                continue
            if layout.depth > 0 and re.search(r"\{\%\s*extends\s+", source):
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
                            "Prefer hx-select on parent for shell layouts."
                        ),
                        template=layout.template_name,
                    )
                )
    return issues
