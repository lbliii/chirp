"""Tests for _viewmodel.py discovery and integration."""

from pathlib import Path

import pytest

from chirp import App, AppConfig
from chirp.pages.discovery import discover_pages
from chirp.testing import TestClient


def test_discovery_finds_viewmodel(tmp_path: Path) -> None:
    """Discovery finds _viewmodel.py with viewmodel() function."""
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    (pages_dir / "_viewmodel.py").write_text(
        """
def viewmodel():
    return {"items": [1, 2, 3]}
"""
    )
    (pages_dir / "page.py").write_text("def get(): return {}")
    (pages_dir / "page.html").write_text("<html></html>")

    routes = discover_pages(pages_dir)
    assert len(routes) == 1
    assert routes[0].viewmodel_provider is not None


def test_discovery_ignores_missing_viewmodel(tmp_path: Path) -> None:
    """Discovery ignores missing _viewmodel.py."""
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    (pages_dir / "page.py").write_text("def get(): return {}")
    (pages_dir / "page.html").write_text("<html></html>")

    routes = discover_pages(pages_dir)
    assert routes[0].viewmodel_provider is None


@pytest.mark.asyncio
async def test_viewmodel_merged_into_context(tmp_path: Path) -> None:
    """Viewmodel output merged into context; handler overrides viewmodel keys."""
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    (pages_dir / "_layout.html").write_text(
        '<html><body id="body">{% block page_root %}{% block content %}{% end %}{% end %}</body></html>'
    )
    (pages_dir / "_viewmodel.py").write_text(
        """
def viewmodel():
    return {"items": [1, 2, 3], "from_vm": "yes"}
"""
    )
    (pages_dir / "page.py").write_text(
        """
from chirp import Page

def get(items, from_vm):
    return Page("page.html", "content", items=items, from_vm=from_vm)
"""
    )
    (pages_dir / "page.html").write_text(
        "{% block page_root %}{% block content %}items={{ items }} vm={{ from_vm }}{% end %}{% end %}"
    )

    app = App(AppConfig(template_dir=str(pages_dir), debug=True))
    app.mount_pages(str(pages_dir))

    async with TestClient(app) as client:
        response = await client.get("/")
    assert response.status == 200
    body = response.body.decode("utf-8")
    assert "[1, 2, 3]" in body or "1, 2, 3" in body
    assert "yes" in body


@pytest.mark.asyncio
async def test_viewmodel_receives_cascade_and_path_params(tmp_path: Path) -> None:
    """Viewmodel receives cascade context, path params, services."""
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
    (child / "_viewmodel.py").write_text(
        """
def viewmodel(name, shared):
    return {"msg": f"{name}:{shared}"}
"""
    )
    (child / "page.py").write_text(
        """
from chirp import Page

def get(name, msg):
    return Page("{name}/page.html", "content", msg=msg)
"""
    )
    (child / "page.html").write_text(
        "{% block page_root %}{% block content %}{{ msg }}{% end %}{% end %}"
    )

    app = App(AppConfig(template_dir=str(pages_dir), debug=True))
    app.mount_pages(str(pages_dir))

    async with TestClient(app) as client:
        response = await client.get("/foo")
    assert response.status == 200
    assert "foo:from-context" in response.body.decode("utf-8")
