"""Tests for RouteMeta and _meta.py discovery."""

from pathlib import Path

import pytest

from chirp.pages.discovery import discover_pages
from chirp.pages.types import RouteMeta


def test_discovery_finds_meta_with_static_constant(tmp_path: Path) -> None:
    """Discovery finds _meta.py with static META constant."""
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    (pages_dir / "_meta.py").write_text(
        """
from chirp.pages.types import RouteMeta

META = RouteMeta(title="Home", section="main")
"""
    )
    (pages_dir / "page.py").write_text(
        """
def get():
    return {}
"""
    )
    (pages_dir / "page.html").write_text("<html></html>")

    routes = discover_pages(pages_dir)
    assert len(routes) == 1
    route = routes[0]
    assert route.meta is not None
    assert route.meta.title == "Home"
    assert route.meta.section == "main"
    assert route.meta_provider is None


def test_discovery_finds_meta_with_dict(tmp_path: Path) -> None:
    """Discovery finds _meta.py with META as dict."""
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    (pages_dir / "_meta.py").write_text(
        """
META = {"title": "Docs", "breadcrumb_label": "Documentation"}
"""
    )
    (pages_dir / "page.py").write_text(
        """
def get():
    return {}
"""
    )
    (pages_dir / "page.html").write_text("<html></html>")

    routes = discover_pages(pages_dir)
    assert len(routes) == 1
    route = routes[0]
    assert route.meta is not None
    assert route.meta.title == "Docs"
    assert route.meta.breadcrumb_label == "Documentation"
    assert route.meta_provider is None


def test_discovery_finds_meta_with_callable(tmp_path: Path) -> None:
    """Discovery finds _meta.py with meta() function."""
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    (pages_dir / "_meta.py").write_text(
        """
from chirp.pages.types import RouteMeta

def meta():
    return RouteMeta(title="Dynamic", section="admin")
"""
    )
    (pages_dir / "page.py").write_text(
        """
def get():
    return {}
"""
    )
    (pages_dir / "page.html").write_text("<html></html>")

    routes = discover_pages(pages_dir)
    assert len(routes) == 1
    route = routes[0]
    assert route.meta is None
    assert route.meta_provider is not None
    assert callable(route.meta_provider)


def test_discovery_ignores_missing_meta(tmp_path: Path) -> None:
    """Discovery ignores missing _meta.py (backward compat)."""
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    (pages_dir / "page.py").write_text(
        """
def get():
    return {}
"""
    )
    (pages_dir / "page.html").write_text("<html></html>")

    routes = discover_pages(pages_dir)
    assert len(routes) == 1
    route = routes[0]
    assert route.meta is None
    assert route.meta_provider is None


def test_discovery_raises_for_invalid_meta(tmp_path: Path) -> None:
    """Discovery raises clear error for invalid _meta.py (no META, no meta())."""
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    (pages_dir / "_meta.py").write_text(
        """
# No META or meta() defined
OTHER = "ignored"
"""
    )
    (pages_dir / "page.py").write_text(
        """
def get():
    return {}
"""
    )
    (pages_dir / "page.html").write_text("<html></html>")

    with pytest.raises(ValueError, match="must define META or meta"):
        discover_pages(pages_dir)


def test_page_route_meta_and_meta_provider_populated(tmp_path: Path) -> None:
    """PageRoute.meta and PageRoute.meta_provider populated correctly."""
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    (pages_dir / "_meta.py").write_text(
        """
from chirp.pages.types import RouteMeta

META = RouteMeta(title="Test", breadcrumb_label="Test Page", tags=("a", "b"))
"""
    )
    (pages_dir / "page.py").write_text(
        """
def get():
    return {}
"""
    )
    (pages_dir / "page.html").write_text("<html></html>")

    routes = discover_pages(pages_dir)
    route = routes[0]
    assert route.meta == RouteMeta(
        title="Test",
        section=None,
        breadcrumb_label="Test Page",
        shell_mode=None,
        auth=None,
        cache=None,
        tags=("a", "b"),
    )
    assert route.meta_provider is None


def test_existing_app_without_meta_produces_identical_page_route(tmp_path: Path) -> None:
    """Existing apps without _meta.py produce identical PageRoute (meta=None)."""
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    (pages_dir / "page.py").write_text(
        """
def get():
    return {}
"""
    )
    (pages_dir / "page.html").write_text("<html></html>")

    routes = discover_pages(pages_dir)
    route = routes[0]
    # Same structure as before: meta and meta_provider are None
    assert hasattr(route, "meta")
    assert hasattr(route, "meta_provider")
    assert route.meta is None
    assert route.meta_provider is None
    assert route.url_path == "/"
    assert route.template_name == "page.html"


def test_route_kind_inference(tmp_path: Path) -> None:
    """Route kind inferred from template + param dir."""
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    (pages_dir / "page.py").write_text("def get(): return {}")
    (pages_dir / "page.html").write_text("<html></html>")
    routes = discover_pages(pages_dir)
    assert routes[0].kind == "page"

    child = pages_dir / "{id}"
    child.mkdir()
    (child / "page.py").write_text("def get(id: str): return {}")
    (child / "page.html").write_text("<html></html>")
    routes = discover_pages(pages_dir)
    detail_route = next(r for r in routes if r.url_path == "/{id}")
    assert detail_route.kind == "detail"

    action_dir = pages_dir / "redirect"
    action_dir.mkdir()
    (action_dir / "page.py").write_text("def post(): return {}")
    routes = discover_pages(pages_dir)
    action_route = next(r for r in routes if r.url_path == "/redirect")
    assert action_route.kind == "action"


def test_meta_not_inherited_by_subdirectory(tmp_path: Path) -> None:
    """Meta is not inherited — subdirectory routes get their own or no meta."""
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    (pages_dir / "_meta.py").write_text(
        """
from chirp.pages.types import RouteMeta

META = RouteMeta(title="Root", section="root")
"""
    )
    (pages_dir / "page.py").write_text("def get(): return {}")
    (pages_dir / "page.html").write_text("<html></html>")

    child_dir = pages_dir / "child"
    child_dir.mkdir()
    # No _meta.py in child
    (child_dir / "page.py").write_text("def get(): return {}")
    (child_dir / "page.html").write_text("<html></html>")

    routes = discover_pages(pages_dir)
    root_route = next(r for r in routes if r.url_path == "/")
    child_route = next(r for r in routes if r.url_path == "/child")

    assert root_route.meta is not None
    assert root_route.meta.title == "Root"
    assert child_route.meta is None
    assert child_route.meta_provider is None
