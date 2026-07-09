"""Tests for route explorer endpoint (/__chirp/routes)."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from chirp import App, AppConfig
from chirp.contracts import FormContract, contract
from chirp.pages.types import Section
from chirp.server.route_explorer import render_route_explorer
from chirp.testing import TestClient


@pytest.fixture
def pages_tree(tmp_path: Path) -> Path:
    """Pages tree with multiple routes."""
    pages = tmp_path / "pages"
    pages.mkdir()
    (pages / "_layout.html").write_text(
        '<html><body id="body"><main>{% block page_root %}{% block content %}{% end %}{% end %}</main></body></html>'
    )
    (pages / "_meta.py").write_text(
        """
from chirp.pages.types import RouteMeta
META = RouteMeta(title="Home", section="main")
"""
    )
    (pages / "page.py").write_text(
        """
from dataclasses import dataclass

from chirp import Page
from chirp.contracts import FormContract, contract


@dataclass(frozen=True, slots=True)
class ReplyForm:
    body: str


def get():
    return Page("page.html", "content")


@contract(form=FormContract(ReplyForm, "page.html", "content"))
def post():
    return Page("page.html", "content")
"""
    )
    (pages / "page.html").write_text(
        '{% block page_root %}{% block content %}<form method="post" action="/"><textarea name="body"></textarea></form>{% end %}{% end %}'
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
    app.register_section(Section(id="main", label="Main"))
    app.register_section(Section(id="discover", label="Discover"))
    app.mount_pages(str(pages_tree))

    async with TestClient(app) as client:
        response = await client.get("/__chirp/routes")

    assert response.status == 200
    body = response.body.decode("utf-8")
    assert "Chirp Route Explorer" in body
    assert "/" in body
    assert "/skills" in body
    assert "page" in body
    assert '<span class="badge">contract</span>' in body
    assert "ReplyForm" in body
    assert "page.html#content" in body
    assert "&quot;has_contract&quot;: true" in body


def test_render_route_explorer_shows_mounted_page_contracts() -> None:
    """Mounted route contracts are visible in route explorer output."""

    class ReplyForm:
        body: str

    @contract(form=FormContract(ReplyForm, "page.html", "content"))
    def post() -> None:
        return None

    body = render_route_explorer(
        [
            SimpleNamespace(
                actions=(),
                context_providers=(),
                handler=post,
                kind="page",
                layout_chain=SimpleNamespace(layouts=()),
                meta=None,
                methods=frozenset({"POST"}),
                template_name="page.html",
                url_path="/",
                viewmodel_provider=None,
            )
        ]
    )
    assert '<span class="badge">contract</span>' in body
    assert "ReplyForm" in body
    assert "page.html#content" in body
    assert "&quot;has_contract&quot;: true" in body


@pytest.mark.asyncio
async def test_route_explorer_404_when_debug_false(pages_tree: Path) -> None:
    """GET /__chirp/routes returns 404 when debug=False."""
    app = App(AppConfig(template_dir=str(pages_tree), debug=False))
    app.mount_pages(str(pages_tree))

    async with TestClient(app) as client:
        response = await client.get("/__chirp/routes")

    assert response.status == 404


@pytest.mark.issue(533)
@pytest.mark.asyncio
async def test_route_explorer_shows_explicit_query_media_types() -> None:
    app = App(AppConfig(debug=True))

    @app.route(
        "/search",
        methods=["QUERY"],
        query_media_types=("application/json",),
    )
    def search() -> str:
        return "ok"

    async with TestClient(app) as client:
        response = await client.get("/__chirp/routes")

    assert response.status == 200
    assert "/search" in response.text
    assert "QUERY" in response.text
    assert "Accept-Query: application/json" in response.text
    assert "&quot;query_media_types&quot;: [" in response.text


@pytest.mark.asyncio
async def test_route_explorer_filter_by_path(pages_tree: Path) -> None:
    """Route explorer filter query param filters routes."""
    app = App(AppConfig(template_dir=str(pages_tree), debug=True))
    app.register_section(Section(id="main", label="Main"))
    app.register_section(Section(id="discover", label="Discover"))
    app.mount_pages(str(pages_tree))

    async with TestClient(app) as client:
        response = await client.get("/__chirp/routes?path=/skills")

    assert response.status == 200
    body = response.body.decode("utf-8")
    assert "/skills" in body
    assert "Chirp Route Explorer" in body
