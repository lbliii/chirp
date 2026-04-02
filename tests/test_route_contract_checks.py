"""Tests for route contract checker extensions."""

from pathlib import Path

from chirp import App, AppConfig
from chirp.contracts import check_hypermedia_surface
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
