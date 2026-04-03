"""Section resolution for route metadata.

Resolves section context (tab_items, breadcrumb_prefix) from RouteMeta.section
and registered sections. Pure function — no side effects.
"""

from __future__ import annotations

from typing import Any

from chirp.pages.types import RouteMeta, Section, TabItem


def _tab_item_to_shell_dict(tab: TabItem) -> dict[str, Any]:
    """Shape for templates and ``tab_is_active`` (chirp-ui route tabs)."""
    row: dict[str, Any] = {"label": tab.label, "href": tab.href}
    if tab.icon is not None:
        row["icon"] = tab.icon
    if tab.badge is not None:
        row["badge"] = tab.badge
    if tab.match != "exact":
        row["match"] = tab.match
    return row


def resolve_section_context(
    meta: RouteMeta | None,
    sections: dict[str, Section],
) -> dict[str, Any]:
    """Resolve section context from RouteMeta.section.

    Returns tab_items and breadcrumb_prefix from the matched section,
    or empty dict if no match (meta is None, section id unknown, or
    section not registered).

    Args:
        meta: Route metadata (may be None).
        sections: Registered sections keyed by id.

    Returns:
        Dict with tab_items and breadcrumb_prefix when section matches,
        otherwise empty dict.
    """
    if meta is None or meta.section is None:
        return {}

    section = sections.get(meta.section)
    if section is None:
        return {}

    result: dict[str, Any] = {}
    if section.tab_items:
        tab_list = [_tab_item_to_shell_dict(t) for t in section.tab_items]
        result["tab_items"] = tab_list
        result["route_tabs"] = tab_list
    if section.breadcrumb_prefix:
        result["breadcrumb_prefix"] = list(section.breadcrumb_prefix)
    return result
