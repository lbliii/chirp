"""Tests for ``{# outlet_mode: #}`` in filesystem layout discovery."""

from __future__ import annotations

from pathlib import Path

import pytest

from chirp.pages.discovery import discover_pages


def _write_minimal_page(pages: Path) -> None:
    (pages / "page.py").write_text(
        "def get():\n    return 'ok'\n",
        encoding="utf-8",
    )
    (pages / "page.html").write_text("<p>x</p>\n", encoding="utf-8")


@pytest.mark.parametrize(
    ("comment", "expected"),
    [
        ("", "compose"),
        ("{# outlet_mode: compose #}\n", "compose"),
        ("{# outlet_mode: replace #}\n", "replace"),
        ("{# outlet_mode: REPLACE #}\n", "replace"),
    ],
)
def test_outlet_mode_parsed_from_layout(
    tmp_path: Path,
    comment: str,
    expected: str,
) -> None:
    pages = tmp_path / "pages"
    pages.mkdir()
    layout = "{# target: body #}\n{# outlet: main #}\n"
    (pages / "_layout.html").write_text(
        comment + layout + "{% block content %}{% end %}\n",
        encoding="utf-8",
    )
    _write_minimal_page(pages)

    routes = discover_pages(pages)
    assert len(routes) == 1
    chain = routes[0].layout_chain
    assert len(chain.layouts) == 1
    assert chain.layouts[0].outlet_mode == expected


def test_outlet_mode_unknown_defaults_to_compose(tmp_path: Path) -> None:
    pages = tmp_path / "pages"
    pages.mkdir()
    (pages / "_layout.html").write_text(
        "{# outlet_mode: banana #}\n{# target: body #}\n{% block content %}{% end %}\n",
        encoding="utf-8",
    )
    _write_minimal_page(pages)

    routes = discover_pages(pages)
    assert routes[0].layout_chain.layouts[0].outlet_mode == "compose"
