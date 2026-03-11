"""Tests for route contract debug headers (X-Chirp-Route-*)."""

from pathlib import Path

import pytest

from chirp import App, AppConfig
from chirp.pages.types import Section, TabItem
from chirp.testing import TestClient


def _header(response: object, name: str) -> str | None:
    """Get header value by name (case-insensitive)."""
    headers = getattr(response, "headers", ())
    for hname, hvalue in headers:
        if hname.lower() == name.lower():
            return hvalue
    return None


@pytest.fixture
def pages_with_meta(tmp_path: Path) -> Path:
    """Pages tree with _meta.py, _context.py, section."""
    pages = tmp_path / "pages"
    pages.mkdir()
    (pages / "_layout.html").write_text(
        '<html><body id="body">{% block page_root %}{% block content %}{% end %}{% end %}</body></html>'
    )
    (pages / "_meta.py").write_text(
        """
from chirp.pages.types import RouteMeta
META = RouteMeta(title="Skills", section="discover", breadcrumb_label="Skills")
"""
    )
    (pages / "_context.py").write_text(
        """
def context():
    return {"extra": "from-context"}
"""
    )
    (pages / "page.py").write_text(
        """
from chirp import Page

def get(extra):
    return Page("page.html", "content", extra=extra)
"""
    )
    (pages / "page.html").write_text(
        '{% block page_root %}{% block content %}{{ extra }}{% end %}{% end %}'
    )
    return pages


@pytest.mark.asyncio
async def test_route_debug_headers_present_when_debug_true(pages_with_meta: Path) -> None:
    """X-Chirp-Route-* headers appear when config.debug=True."""
    app = App(AppConfig(template_dir=str(pages_with_meta), debug=True))
    app.register_section(
        Section(
            id="discover",
            label="Discover",
            tab_items=(TabItem(label="Skills", href="/"),),
        )
    )
    app.mount_pages(str(pages_with_meta))

    async with TestClient(app) as client:
        response = await client.get("/")

    assert response.status == 200
    assert _header(response, "X-Chirp-Route-Kind") == "page"
    assert "page.py" in (_header(response, "X-Chirp-Route-Files") or "")
    assert "Skills" in (_header(response, "X-Chirp-Route-Meta") or "")
    assert _header(response, "X-Chirp-Route-Section") == "discover"
    assert _header(response, "X-Chirp-Shell-Context") is not None


@pytest.mark.asyncio
async def test_route_debug_headers_absent_when_debug_false(pages_with_meta: Path) -> None:
    """X-Chirp-Route-* headers are absent when config.debug=False."""
    app = App(AppConfig(template_dir=str(pages_with_meta), debug=False))
    app.mount_pages(str(pages_with_meta))

    async with TestClient(app) as client:
        response = await client.get("/")

    assert response.status == 200
    assert _header(response, "X-Chirp-Route-Kind") is None
    assert _header(response, "X-Chirp-Route-Files") is None
    assert _header(response, "X-Chirp-Route-Meta") is None


@pytest.mark.asyncio
async def test_route_debug_headers_on_non_page_route(tmp_path: Path) -> None:
    """Non-page routes (e.g. @app.route) do not get route debug headers."""
    app = App(AppConfig(template_dir=str(tmp_path), debug=True))

    @app.route("/api/ok", methods=["GET"])
    def api_ok():
        return "ok"

    async with TestClient(app) as client:
        response = await client.get("/api/ok")

    assert response.status == 200
    assert _header(response, "X-Chirp-Route-Kind") is None
