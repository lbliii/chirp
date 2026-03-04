"""Tests for context cascade: parent context passed to child providers."""

from pathlib import Path

import pytest

from chirp import App, AppConfig
from chirp.testing import TestClient


def _create_cascade_app(tmp_path: Path) -> App:
    """Create app with root + child context cascade (parent provides shared to child)."""
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()

    # Root layout
    (pages_dir / "_layout.html").write_text(
        '<html><body id="body">{% block content %}{% end %}</body></html>'
    )

    # Root context: provides shared value
    (pages_dir / "_context.py").write_text(
        """
def context() -> dict:
    return {"shared": "from-root"}
"""
    )

    # doc/{id}/ structure
    doc_id_dir = pages_dir / "doc" / "{id}"
    doc_id_dir.mkdir(parents=True)

    # Child context: receives id from path, shared from parent
    (doc_id_dir / "_context.py").write_text(
        """
def context(id: str, shared: str) -> dict:
    return {"doc_id": id, "shared": shared}
"""
    )

    # Page handler: receives doc_id and shared from cascade
    (doc_id_dir / "page.py").write_text(
        """
from chirp import Page

def get(doc_id: str, shared: str) -> Page:
    return Page("doc/{id}/page.html", "content", doc_id=doc_id, shared=shared)
"""
    )

    (doc_id_dir / "page.html").write_text(
        '{% block content %}<span id="doc_id">{{ doc_id }}</span>'
        '<span id="shared">{{ shared }}</span>{% end %}'
    )

    app = App(AppConfig(template_dir=str(pages_dir), debug=True))
    app.mount_pages(str(pages_dir))
    return app


class TestContextCascade:
    """Child providers receive path params and parent context."""

    @pytest.mark.asyncio
    async def test_child_receives_parent_context(self, tmp_path: Path) -> None:
        """Child context(id, shared) receives id from path and shared from root."""
        app = _create_cascade_app(tmp_path)

        async with TestClient(app) as client:
            response = await client.get("/doc/foo")

        assert response.status == 200
        body = response.body.decode("utf-8")
        assert "foo" in body
        assert "from-root" in body
