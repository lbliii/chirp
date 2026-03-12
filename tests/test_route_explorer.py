"""Tests for route explorer endpoint (/__chirp/routes)."""

from pathlib import Path

import pytest

from chirp import App, AppConfig
from chirp.testing import TestClient


@pytest.fixture
def pages_tree(tmp_path: Path) -> Path:
    """Pages tree with multiple routes."""
    pages = tmp_path / "pages"
    pages.mkdir()
    (pages / "_layout.html").write_text(
        '<html><body id="body">{% block page_root %}{% block content %}{% end %}{% end %}</body></html>'
    )
    (pages / "_meta.py").write_text(
        """
from chirp.pages.types import RouteMeta
META = RouteMeta(title="Home", section="main")
"""
    )
    (pages / "page.py").write_text(
        """
from chirp import Page
def get():
    return Page("page.html", "content")
"""
    )
    (pages / "page.html").write_text(
        "{% block page_root %}{% block content %}home{% end %}{% end %}"
    )
    skills = pages / "skills"
    skills.mkdir()
    (skills / "_meta.py").write_text(
        """
from chirp.pages.types import RouteMeta
META = RouteMeta(title="Skills", section="discover")
"""
    )
    (skills / "page.py").write_text(
        """
from chirp import Page
def get():
    return Page("page.html", "content")
"""
    )
    (skills / "page.html").write_text(
        "{% block page_root %}{% block content %}skills{% end %}{% end %}"
    )
    return pages


@pytest.mark.asyncio
async def test_route_explorer_200_when_debug_true(pages_tree: Path) -> None:
    """GET /__chirp/routes returns 200 with route data when debug=True."""
    app = App(AppConfig(template_dir=str(pages_tree), debug=True))
    app.mount_pages(str(pages_tree))

    async with TestClient(app) as client:
        response = await client.get("/__chirp/routes")

    assert response.status == 200
    body = response.body.decode("utf-8")
    assert "Chirp Route Explorer" in body
    assert "/" in body
    assert "/skills" in body
    assert "page" in body


@pytest.mark.asyncio
async def test_route_explorer_404_when_debug_false(pages_tree: Path) -> None:
    """GET /__chirp/routes returns 404 when debug=False."""
    app = App(AppConfig(template_dir=str(pages_tree), debug=False))
    app.mount_pages(str(pages_tree))

    async with TestClient(app) as client:
        response = await client.get("/__chirp/routes")

    assert response.status == 404


@pytest.mark.asyncio
async def test_route_explorer_filter_by_path(pages_tree: Path) -> None:
    """Route explorer filter query param filters routes."""
    app = App(AppConfig(template_dir=str(pages_tree), debug=True))
    app.mount_pages(str(pages_tree))

    async with TestClient(app) as client:
        response = await client.get("/__chirp/routes?path=/skills")

    assert response.status == 200
    body = response.body.decode("utf-8")
    assert "/skills" in body
    assert "Chirp Route Explorer" in body
