"""Tests for ``{# shell: #}`` layout discovery and inherited shell paths."""

from __future__ import annotations

from pathlib import Path

from chirp.pages.discovery import discover_pages


def _write_page(directory: Path) -> None:
    (directory / "page.py").write_text(
        "def get():\n    return 'ok'\n",
        encoding="utf-8",
    )
    (directory / "page.html").write_text("<p>x</p>\n", encoding="utf-8")


def test_shell_comment_is_parsed_from_layout(tmp_path: Path) -> None:
    pages = tmp_path / "pages"
    pages.mkdir()
    (pages / "_layout.html").write_text(
        '{# target: body #}\n{# shell: site #}\n{% block content %}{% end %}\n',
        encoding="utf-8",
    )
    _write_page(pages)

    routes = discover_pages(pages)
    assert len(routes) == 1
    chain = routes[0].layout_chain
    assert len(chain.layouts) == 1
    assert chain.layouts[0].shell_name == "site"
    assert chain.shell_path == ("site",)


def test_shell_path_inherits_from_ancestor_layouts(tmp_path: Path) -> None:
    pages = tmp_path / "pages"
    showcase = pages / "showcase"
    pages.mkdir()
    showcase.mkdir()
    (pages / "_layout.html").write_text(
        '{# target: body #}\n{# shell: site #}\n{% block content %}{% end %}\n',
        encoding="utf-8",
    )
    (showcase / "_layout.html").write_text(
        '{# target: main #}\n{# shell: showcase #}\n{% block content %}{% end %}\n',
        encoding="utf-8",
    )
    _write_page(showcase)

    routes = discover_pages(pages)
    assert len(routes) == 1
    chain = routes[0].layout_chain
    assert tuple(layout.shell_name for layout in chain.layouts) == ("site", "showcase")
    assert chain.shell_path == ("site", "showcase")
