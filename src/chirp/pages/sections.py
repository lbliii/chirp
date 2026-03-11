"""Section resolution for route metadata.

Resolves section context (tab_items, breadcrumb_prefix) from RouteMeta.section
and registered sections. Pure function — no side effects.
"""

from __future__ import annotations

from typing import Any

from chirp.pages.types import RouteMeta, Section


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
        result["tab_items"] = [
            {"label": t.label, "href": t.href} for t in section.tab_items
        ]
    if section.breadcrumb_prefix:
        result["breadcrumb_prefix"] = list(section.breadcrumb_prefix)
    return result
