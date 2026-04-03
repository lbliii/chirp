"""Tests for route contract checker extensions."""

from pathlib import Path

from chirp import App, AppConfig
from chirp.contracts import check_hypermedia_surface
from chirp.contracts.types import Severity
from chirp.pages.types import Section, TabItem


def test_unknown_section_produces_warning(tmp_path: Path) -> None:
    """Unknown section id produces warning."""
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    (pages_dir / "_meta.py").write_text(
        """
from chirp.pages.types import RouteMeta
META = RouteMeta(section="unknown-section")
"""
    )
    (pages_dir / "page.py").write_text("def get(): return {}")
    (pages_dir / "page.html").write_text("<html></html>")

    app = App(AppConfig(template_dir=str(pages_dir), debug=True))
    app.mount_pages(str(pages_dir))

    # check() with warnings_as_errors=False allows warnings through
    app.check(warnings_as_errors=False)


def test_route_without_meta_produces_info(tmp_path: Path) -> None:
    """Route without _meta.py produces info (no error)."""
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    (pages_dir / "page.py").write_text("def get(): return {}")
    (pages_dir / "page.html").write_text("<html></html>")

    app = App(AppConfig(template_dir=str(pages_dir), debug=True))
    app.mount_pages(str(pages_dir))

    # Should not raise
    app.check(warnings_as_errors=False)


def test_section_tab_prefix_href_matches_child_routes(tmp_path: Path) -> None:
    """Prefix tab href /docs is satisfied by /docs and /docs/guide routes."""
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    docs = pages_dir / "docs"
    docs.mkdir()
    (docs / "page.py").write_text("def get(): return {}")
    (docs / "page.html").write_text("<html></html>")
    guide = docs / "guide"
    guide.mkdir()
    (guide / "page.py").write_text("def get(): return {}")
    (guide / "page.html").write_text("<html></html>")

    app = App(AppConfig(template_dir=str(pages_dir), debug=True))
    app.register_section(
        Section(
            id="docs",
            label="Docs",
            tab_items=(TabItem(label="Docs home", href="/docs", match="prefix"),),
        )
    )
    app.mount_pages(str(pages_dir))

    result = check_hypermedia_surface(app)
    tab_issues = [
        i
        for i in result.issues
        if getattr(i, "category", None) == "route_contract"
        and "tab href" in (i.message or "").lower()
    ]
    assert tab_issues == []


def test_section_tab_href_warning(tmp_path: Path) -> None:
    """Section tab href that doesn't match any route produces warning."""
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    (pages_dir / "page.py").write_text("def get(): return {}")
    (pages_dir / "page.html").write_text("<html></html>")

    app = App(AppConfig(template_dir=str(pages_dir), debug=True))
    app.register_section(
        Section(
            id="main",
            label="Main",
            tab_items=(
                TabItem(label="Home", href="/"),
                TabItem(label="Missing", href="/nonexistent"),
            ),
        )
    )
    app.mount_pages(str(pages_dir))

    result = check_hypermedia_surface(app)
    route_issues = [i for i in result.issues if getattr(i, "category", None) == "route_contract"]
    tab_issues = [i for i in route_issues if "tab href" in (i.message or "").lower()]
    assert len(tab_issues) >= 1
    assert "/nonexistent" in (tab_issues[0].message or "")


def test_dynamic_meta_callable_skips_missing_meta_info(tmp_path: Path) -> None:
    """Routes with ``meta()`` in _meta.py must not emit 'no _meta.py' info."""
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    item = pages_dir / "item" / "{id}"
    item.mkdir(parents=True)
    (item / "_meta.py").write_text(
        """
from chirp.pages.types import RouteMeta

def meta(id: str) -> RouteMeta:
    return RouteMeta(title=id, section="main")
"""
    )
    (item / "page.py").write_text("def get(id): return {}")
    (item / "page.html").write_text("<html></html>")

    app = App(AppConfig(template_dir=str(pages_dir), debug=True))
    app.register_section(Section(id="main", label="Main"))
    app.mount_pages(str(pages_dir))

    result = check_hypermedia_surface(app)
    no_meta = [
        i
        for i in result.issues
        if getattr(i, "category", None) == "route_contract"
        and i.route == "/item/{id}"
        and i.message
        and "no _meta.py" in i.message
    ]
    assert no_meta == []


def test_dynamic_meta_skips_section_coverage_info(tmp_path: Path) -> None:
    """Routes with ``meta()`` must not emit 'no meta.section' section-coverage INFO."""
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    item = pages_dir / "docs" / "item" / "{id}"
    item.mkdir(parents=True)
    (item / "_meta.py").write_text(
        """
from chirp.pages.types import RouteMeta

def meta(id: str) -> RouteMeta:
    return RouteMeta(title=id, section="docs")
"""
    )
    (item / "page.py").write_text("def get(id): return {}")
    (item / "page.html").write_text("<html></html>")

    app = App(AppConfig(template_dir=str(pages_dir), debug=True))
    app.register_section(
        Section(id="docs", label="Docs", active_prefixes=("/docs",)),
    )
    app.mount_pages(str(pages_dir))

    result = check_hypermedia_surface(app)
    missing_section_info = [
        i
        for i in result.issues
        if getattr(i, "category", None) == "route_contract"
        and i.route == "/docs/item/{id}"
        and i.message
        and "active_prefixes" in i.message
        and "meta.section" in i.message
    ]
    assert missing_section_info == []


def test_known_section_passes(tmp_path: Path) -> None:
    """Route with known section passes section binding check."""
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    (pages_dir / "_meta.py").write_text(
        """
from chirp.pages.types import RouteMeta
META = RouteMeta(section="main")
"""
    )
    (pages_dir / "page.py").write_text("def get(): return {}")
    (pages_dir / "page.html").write_text("<html></html>")

    app = App(AppConfig(template_dir=str(pages_dir), debug=True))
    app.register_section(Section(id="main", label="Main"))
    app.mount_pages(str(pages_dir))

    app.check(warnings_as_errors=False)


def test_duplicate_tab_hrefs_in_section_warn(tmp_path: Path) -> None:
    """Two tabs with the same normalized href in one section emit a warning."""
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    (pages_dir / "page.py").write_text("def get(): return {}")
    (pages_dir / "page.html").write_text("<html></html>")

    app = App(AppConfig(template_dir=str(pages_dir), debug=True))
    app.register_section(
        Section(
            id="main",
            label="Main",
            tab_items=(
                TabItem(label="Home A", href="/"),
                TabItem(label="Home B", href="/"),
            ),
        )
    )
    app.mount_pages(str(pages_dir))

    result = check_hypermedia_surface(app)
    dup = [
        i
        for i in result.issues
        if getattr(i, "category", None) == "route_contract"
        and i.message
        and "duplicate tab href" in i.message.lower()
    ]
    assert len(dup) >= 1


def test_section_tab_prefix_href_matches_parametric_only_route(tmp_path: Path) -> None:
    """Prefix tab at /docs is satisfied when the only route is /docs/{slug}."""
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    slug = pages_dir / "docs" / "{slug}"
    slug.mkdir(parents=True)
    (slug / "page.py").write_text("def get(slug): return {}")
    (slug / "page.html").write_text("<html></html>")

    app = App(AppConfig(template_dir=str(pages_dir), debug=True))
    app.register_section(
        Section(
            id="docs",
            label="Docs",
            tab_items=(TabItem(label="Docs", href="/docs", match="prefix"),),
        )
    )
    app.mount_pages(str(pages_dir))

    result = check_hypermedia_surface(app)
    tab_issues = [
        i
        for i in result.issues
        if getattr(i, "category", None) == "route_contract"
        and "tab href" in (i.message or "").lower()
    ]
    assert tab_issues == []


def test_route_under_section_prefix_without_meta_section_info(tmp_path: Path) -> None:
    """Route under active_prefixes with no meta.section emits INFO."""
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    docs = pages_dir / "docs"
    docs.mkdir()
    (docs / "page.py").write_text("def get(): return {}")
    (docs / "page.html").write_text("<html></html>")

    app = App(AppConfig(template_dir=str(pages_dir), debug=True))
    app.register_section(
        Section(id="docs", label="Docs", active_prefixes=("/docs",)),
    )
    app.mount_pages(str(pages_dir))

    result = check_hypermedia_surface(app)
    unclaimed = [
        i
        for i in result.issues
        if getattr(i, "category", None) == "route_contract"
        and i.message
        and "active_prefixes" in i.message
        and "meta.section" in i.message
    ]
    assert len(unclaimed) >= 1
    assert unclaimed[0].severity == Severity.INFO


def test_meta_section_not_covering_path_warns(tmp_path: Path) -> None:
    """meta.section that does not cover the route path emits WARNING."""
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    other = pages_dir / "other"
    other.mkdir()
    (other / "_meta.py").write_text(
        """
from chirp.pages.types import RouteMeta
META = RouteMeta(section="docs")
"""
    )
    (other / "page.py").write_text("def get(): return {}")
    (other / "page.html").write_text("<html></html>")

    app = App(AppConfig(template_dir=str(pages_dir), debug=True))
    app.register_section(
        Section(id="docs", label="Docs", active_prefixes=("/docs",)),
    )
    app.mount_pages(str(pages_dir))

    result = check_hypermedia_surface(app)
    mismatched = [
        i
        for i in result.issues
        if getattr(i, "category", None) == "route_contract"
        and i.message
        and "active_prefixes do not cover" in i.message
    ]
    assert len(mismatched) >= 1
    assert mismatched[0].severity == Severity.WARNING


def test_section_coverage_clean_when_meta_matches_prefixes(tmp_path: Path) -> None:
    """Route path covered by section active_prefixes with matching meta.section is clean."""
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    docs = pages_dir / "docs"
    docs.mkdir()
    (docs / "_meta.py").write_text(
        """
from chirp.pages.types import RouteMeta
META = RouteMeta(section="docs")
"""
    )
    (docs / "page.py").write_text("def get(): return {}")
    (docs / "page.html").write_text("<html></html>")

    app = App(AppConfig(template_dir=str(pages_dir), debug=True))
    app.register_section(
        Section(id="docs", label="Docs", active_prefixes=("/docs",)),
    )
    app.mount_pages(str(pages_dir))

    result = check_hypermedia_surface(app)
    coverage_issues = [
        i
        for i in result.issues
        if getattr(i, "category", None) == "route_contract"
        and i.message
        and (
            ("active_prefixes" in i.message and "meta.section" in i.message)
            or "active_prefixes do not cover" in i.message
        )
    ]
    assert coverage_issues == []


def test_route_not_under_any_section_no_coverage_issue(tmp_path: Path) -> None:
    """Route outside all section prefixes does not emit section coverage issues."""
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    (pages_dir / "page.py").write_text("def get(): return {}")
    (pages_dir / "page.html").write_text("<html></html>")

    app = App(AppConfig(template_dir=str(pages_dir), debug=True))
    app.register_section(
        Section(id="admin", label="Admin", active_prefixes=("/admin",)),
    )
    app.mount_pages(str(pages_dir))

    result = check_hypermedia_surface(app)
    coverage_issues = [
        i
        for i in result.issues
        if getattr(i, "category", None) == "route_contract"
        and i.message
        and (
            ("active_prefixes" in i.message and "meta.section" in i.message)
            or "active_prefixes do not cover" in i.message
        )
    ]
    assert coverage_issues == []
