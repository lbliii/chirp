"""Tests for section registry and resolve_section_context."""

from chirp.pages.sections import resolve_section_context
from chirp.pages.types import RouteMeta, Section, TabItem


def test_register_section_lookup() -> None:
    """Register section, look up by id."""
    section = Section(
        id="admin",
        label="Admin",
        tab_items=(TabItem(label="Users", href="/admin/users"),),
    )
    sections = {"admin": section}
    meta = RouteMeta(section="admin")
    result = resolve_section_context(meta, sections)
    assert "tab_items" in result
    assert result["tab_items"] == [{"label": "Users", "href": "/admin/users"}]


def test_resolve_section_context_with_matching_section() -> None:
    """resolve_section_context with matching section returns tab_items + breadcrumb_prefix."""
    section = Section(
        id="docs",
        label="Documentation",
        tab_items=(
            TabItem(label="Guide", href="/docs/guide"),
            TabItem(label="API", href="/docs/api"),
        ),
        breadcrumb_prefix=(
            {"label": "Docs", "href": "/docs"},
        ),
    )
    sections = {"docs": section}
    meta = RouteMeta(section="docs", title="Guide")

    result = resolve_section_context(meta, sections)
    assert result["tab_items"] == [
        {"label": "Guide", "href": "/docs/guide"},
        {"label": "API", "href": "/docs/api"},
    ]
    assert result["breadcrumb_prefix"] == [{"label": "Docs", "href": "/docs"}]


def test_resolve_section_context_with_no_section() -> None:
    """resolve_section_context with no section returns empty dict."""
    sections = {"admin": Section(id="admin", label="Admin")}
    meta = RouteMeta(title="Home")  # meta.section is None

    result = resolve_section_context(meta, sections)
    assert result == {}


def test_resolve_section_context_with_none_meta() -> None:
    """resolve_section_context with None meta returns empty dict."""
    sections = {"admin": Section(id="admin", label="Admin")}
    result = resolve_section_context(None, sections)
    assert result == {}


def test_resolve_section_context_with_unknown_section_id() -> None:
    """resolve_section_context with unknown section id returns empty dict."""
    sections = {"admin": Section(id="admin", label="Admin")}
    meta = RouteMeta(section="unknown")

    result = resolve_section_context(meta, sections)
    assert result == {}


def test_resolve_section_context_section_active_prefixes() -> None:
    """Section.active_prefixes matching logic — section still resolves."""
    section = Section(
        id="collections",
        label="Collections",
        tab_items=(TabItem(label="List", href="/collections"),),
        active_prefixes=("/collections", "/collections/"),
    )
    sections = {"collections": section}
    meta = RouteMeta(section="collections")

    result = resolve_section_context(meta, sections)
    assert "tab_items" in result
    assert result["tab_items"] == [{"label": "List", "href": "/collections"}]
