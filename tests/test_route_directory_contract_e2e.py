"""E2E tests for Route Directory Contract — full pages tree with all new files."""

from pathlib import Path

import pytest

from chirp import App, AppConfig
from chirp.pages.types import Section, TabItem
from chirp.testing import TestClient


@pytest.fixture
def full_pages_tree(tmp_path: Path) -> Path:
    """Build a tmp_path pages tree with _meta.py, _actions.py, _viewmodel.py, etc."""
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()

    (pages_dir / "_layout.html").write_text(
        '<html><body id="body">{% block page_root %}{% block content %}{% end %}{% end %}</body></html>'
    )
    (pages_dir / "_meta.py").write_text(
        """
from chirp.pages.types import RouteMeta
META = RouteMeta(title="Home", section="main", breadcrumb_label="Home")
"""
    )
    (pages_dir / "_context.py").write_text(
        """
def context():
    return {"app": "e2e"}
"""
    )
    (pages_dir / "_viewmodel.py").write_text(
        """
def viewmodel():
    return {"items": [1, 2, 3]}
"""
    )
    (pages_dir / "_actions.py").write_text(
        """
from chirp.pages.actions import action

@action("save")
def save():
    return {"msg": "saved"}
"""
    )
    (pages_dir / "page.py").write_text(
        """
from chirp import Page

def get(items, app):
    return Page("page.html", "content", items=items, app=app, page_title="Home")
def post():
    return Page("page.html", "content", msg="post")
"""
    )
    (pages_dir / "page.html").write_text(
        "{% block page_root %}{% block content %}"
        '{{ page_title or "no-title" }}|{{ items }}|{{ app }}{% if msg | default("") %}|{{ msg }}{% end %}'
        "{% end %}{% end %}"
    )
    return pages_dir


@pytest.mark.asyncio
async def test_full_page_renders_with_shell_context(full_pages_tree: Path) -> None:
    """Full-page request renders with correct page_title, breadcrumb_items, tab_items."""
    app = App(AppConfig(template_dir=str(full_pages_tree), debug=True))
    app.register_section(
        Section(
            id="main",
            label="Main",
            tab_items=(TabItem(label="Home", href="/"),),
            breadcrumb_prefix=({"label": "App", "href": "/"},),
        )
    )
    app.mount_pages(str(full_pages_tree))

    async with TestClient(app) as client:
        response = await client.get("/")
    assert response.status == 200
    body = response.body.decode("utf-8")
    assert "Home" in body
    assert "[1, 2, 3]" in body or "1, 2, 3" in body
    assert "e2e" in body


@pytest.mark.asyncio
async def test_action_dispatch_in_e2e(full_pages_tree: Path) -> None:
    """Action dispatch works in full app."""
    app = App(AppConfig(template_dir=str(full_pages_tree), debug=True))
    app.mount_pages(str(full_pages_tree))

    async with TestClient(app) as client:
        response = await client.post("/", data={"_action": "save"})
    assert response.status == 200
    assert "saved" in response.body.decode("utf-8")


@pytest.mark.asyncio
async def test_viewmodel_merges_in_e2e(full_pages_tree: Path) -> None:
    """Viewmodel merges correctly into context."""
    app = App(AppConfig(template_dir=str(full_pages_tree), debug=True))
    app.mount_pages(str(full_pages_tree))

    async with TestClient(app) as client:
        response = await client.get("/")
    assert response.status == 200
    assert "1" in response.body.decode("utf-8")  # items from viewmodel


@pytest.mark.asyncio
async def test_app_check_passes(full_pages_tree: Path) -> None:
    """app.check() passes with no errors."""
    app = App(AppConfig(template_dir=str(full_pages_tree), debug=True))
    app.register_section(Section(id="main", label="Main"))
    app.mount_pages(str(full_pages_tree))

    app.check(warnings_as_errors=False)


def test_backward_compat_app_without_new_files(tmp_path: Path) -> None:
    """Existing app without any new files produces identical behavior."""
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    (pages_dir / "_layout.html").write_text(
        '<html><body id="body">{% block page_root %}{% block content %}{% end %}{% end %}</body></html>'
    )
    (pages_dir / "page.py").write_text(
        """
from chirp import Page
def get():
    return Page("page.html", "content", msg="hello")
"""
    )
    (pages_dir / "page.html").write_text(
        "{% block page_root %}{% block content %}{{ msg }}{% end %}{% end %}"
    )

    app = App(AppConfig(template_dir=str(pages_dir), debug=True))
    app.mount_pages(str(pages_dir))

    # No _meta, _actions, _viewmodel — should work as before
    import asyncio

    async def _():
        async with TestClient(app) as client:
            r = await client.get("/")
            assert r.status == 200
            assert "hello" in r.body.decode("utf-8")

    asyncio.run(_())
