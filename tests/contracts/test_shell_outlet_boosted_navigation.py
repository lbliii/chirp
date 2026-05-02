"""Boosted shell-outlet navigation contracts."""

from pathlib import Path

import pytest

from chirp import App, AppConfig, use_chirp_ui
from chirp.testing import TestClient


def _write_shell_outlet_app(pages: Path, *, outlet: bool = True) -> None:
    pages.mkdir()
    outlet_comment = "{# outlet: main #}\n" if outlet else ""
    (pages / "_layout.html").write_text(
        "{# target: body #}\n"
        f"{outlet_comment}"
        "<!DOCTYPE html><html><body>"
        '<main id="main" hx-boost="true" hx-target="#main" '
        'hx-swap="innerHTML" hx-select="#page-content">'
        '<div id="page-content">{% block content %}{% end %}</div>'
        "</main>"
        "</body></html>",
        encoding="utf-8",
    )
    (pages / "page.py").write_text(
        "from chirp import Page\n\n"
        "def get():\n"
        '    return Page("page.html", "page_content", page_block_name="page_root", '
        'message="Ready")\n',
        encoding="utf-8",
    )
    (pages / "page.html").write_text(
        '{% block page_root %}<div id="page-root">'
        "{% block page_root_inner %}"
        "{% block page_content %}<p>{{ message }}</p>{% end %}"
        "{% end %}"
        "</div>{% end %}",
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_boosted_navigation_to_shell_outlet_includes_selectable_page_content(
    tmp_path: Path,
) -> None:
    pages = tmp_path / "pages"
    _write_shell_outlet_app(pages)

    app = App(AppConfig(template_dir=str(pages), debug=True))
    app.register_fragment_target("main", fragment_block="page_root", scope_name="shell")
    app.register_swap_scope("shell", "main")
    app.mount_pages(str(pages))

    async with TestClient(app) as client:
        response = await client.fragment(
            "/",
            target="main",
            headers={"HX-Boosted": "true"},
        )

    assert response.status == 200
    assert 'id="page-content"' in response.text
    assert 'id="page-root"' in response.text
    assert "Ready" in response.text


@pytest.mark.asyncio
async def test_chirpui_app_shell_extends_infers_main_outlet_for_boosted_navigation(
    tmp_path: Path,
) -> None:
    pages = tmp_path / "pages"
    pages.mkdir()
    (pages / "_layout.html").write_text(
        '{# target: body #}\n{% extends "chirpui/app_shell_layout.html" %}\n'
        "{% block brand %}Forum{% end %}\n"
        "{% block sidebar %}<nav>Boards</nav>{% end %}\n",
        encoding="utf-8",
    )
    (pages / "page.py").write_text(
        "from chirp import Page\n\n"
        "def get():\n"
        '    return Page("page.html", "page_content", page_block_name="page_root", '
        'message="Ready")\n',
        encoding="utf-8",
    )
    (pages / "page.html").write_text(
        '{% block page_root %}<div id="page-root">'
        "{% block page_root_inner %}"
        "{% block page_content %}<p>{{ message }}</p>{% end %}"
        "{% end %}"
        "</div>{% end %}",
        encoding="utf-8",
    )

    app = App(AppConfig(template_dir=str(pages), debug=True))
    use_chirp_ui(app)
    app.mount_pages(str(pages))

    async with TestClient(app) as client:
        response = await client.fragment(
            "/",
            target="main",
            headers={"HX-Boosted": "true"},
        )

    assert response.status == 200
    assert 'id="page-content"' in response.text
    assert 'id="page-root"' in response.text
    assert "Ready" in response.text
