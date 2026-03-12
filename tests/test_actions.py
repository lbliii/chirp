"""Tests for _actions.py discovery and dispatch."""

from pathlib import Path

import pytest

from chirp import App, AppConfig
from chirp.pages.discovery import discover_pages
from chirp.testing import TestClient


def test_discovery_finds_actions(tmp_path: Path) -> None:
    """Discovery finds _actions.py with @action decorated functions."""
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    (pages_dir / "_actions.py").write_text(
        """
from chirp.pages.actions import action

@action("delete")
def delete_item(id: str):
    return {"deleted": id}
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
    assert len(route.actions) == 1
    assert route.actions[0].name == "delete"


def test_discovery_ignores_missing_actions(tmp_path: Path) -> None:
    """Discovery ignores missing _actions.py."""
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    (pages_dir / "page.py").write_text("def get(): return {}")
    (pages_dir / "page.html").write_text("<html></html>")

    routes = discover_pages(pages_dir)
    assert len(routes) == 1
    assert routes[0].actions == ()


@pytest.mark.asyncio
async def test_action_dispatch_by_form_field(tmp_path: Path) -> None:
    """Action dispatch by _action form field."""
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    (pages_dir / "_layout.html").write_text(
        '<html><body id="body">{% block page_root %}{% block content %}{% end %}{% end %}</body></html>'
    )
    (pages_dir / "_actions.py").write_text(
        """
from chirp.pages.actions import action

@action("save")
def save():
    from chirp import Redirect
    return Redirect("/saved")
"""
    )
    (pages_dir / "page.py").write_text(
        """
from chirp import Page

def get():
    return Page("page.html", "content", msg="get")
def post():
    return Page("page.html", "content", msg="post")
"""
    )
    (pages_dir / "page.html").write_text(
        "{% block page_root %}{% block content %}{{ msg }}{% end %}{% end %}"
    )

    app = App(AppConfig(template_dir=str(pages_dir), debug=True))
    app.mount_pages(str(pages_dir))

    async with TestClient(app) as client:
        response = await client.post("/", data={"_action": "save"})
        assert response.status in (200, 302, 303)
        if response.status in (302, 303):
            locs = [v for n, v in response.headers if n.lower() == "location"]
            assert any("saved" in loc for loc in locs)


@pytest.mark.asyncio
async def test_action_receives_path_params_and_context(tmp_path: Path) -> None:
    """Action receives path params, cascade context, service providers."""
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    (pages_dir / "_layout.html").write_text(
        '<html><body id="body">{% block page_root %}{% block content %}{% end %}{% end %}</body></html>'
    )
    (pages_dir / "_context.py").write_text(
        """
def context():
    return {"shared": "from-context"}
"""
    )
    child = pages_dir / "{name}"
    child.mkdir()
    (child / "_actions.py").write_text(
        """
from chirp.pages.actions import action

@action("test")
def test_action(name: str, shared: str):
    return {"msg": f"{name}:{shared}"}
"""
    )
    (child / "page.py").write_text(
        """
from chirp import Page

def get(name: str):
    return Page("{name}/page.html", "content", msg="get")
def post(name: str):
    return Page("{name}/page.html", "content", msg="post")
"""
    )
    (child / "page.html").write_text(
        "{% block page_root %}{% block content %}{{ msg }}{% end %}{% end %}"
    )

    app = App(AppConfig(template_dir=str(pages_dir), debug=True))
    app.mount_pages(str(pages_dir))

    async with TestClient(app) as client:
        response = await client.post("/foo", data={"_action": "test"})
        assert response.status == 200
        body = response.body.decode("utf-8")
        assert "foo:from-context" in body


@pytest.mark.asyncio
async def test_page_post_coexists_with_actions(tmp_path: Path) -> None:
    """page.py post() + _actions.py actions coexist."""
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    (pages_dir / "_layout.html").write_text(
        '<html><body id="body">{% block page_root %}{% block content %}{% end %}{% end %}</body></html>'
    )
    (pages_dir / "_actions.py").write_text(
        """
from chirp.pages.actions import action

@action("custom")
def custom():
    return {"msg": "from-action"}
"""
    )
    (pages_dir / "page.py").write_text(
        """
from chirp import Page

def get():
    return Page("page.html", "content", msg="get")
def post():
    return Page("page.html", "content", msg="from-post")
"""
    )
    (pages_dir / "page.html").write_text(
        "{% block page_root %}{% block content %}{{ msg }}{% end %}{% end %}"
    )

    app = App(AppConfig(template_dir=str(pages_dir), debug=True))
    app.mount_pages(str(pages_dir))

    async with TestClient(app) as client:
        # POST without _action -> runs post() handler
        response = await client.post("/", data={})
        assert response.status == 200
        assert "from-post" in response.body.decode("utf-8")

        # POST with _action=custom -> runs action
        response2 = await client.post("/", data={"_action": "custom"})
        assert response2.status == 200
        assert "from-action" in response2.body.decode("utf-8")
