"""Tests for layout discovery, shell ancestry, and navigation domains."""

from __future__ import annotations

from pathlib import Path

import pytest

from chirp.pages.discovery import discover_pages
from chirp.pages.types import LayoutPreset


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
        "{# target: body #}\n{# shell: site #}\n{% block content %}{% end %}\n",
        encoding="utf-8",
    )
    _write_page(pages)

    routes = discover_pages(pages)
    assert len(routes) == 1
    chain = routes[0].layout_chain
    assert len(chain.layouts) == 1
    assert chain.layouts[0].shell_name == "site"
    assert chain.domain_path == ()
    assert chain.shell_path == ("site",)
    assert chain.navigation_domain_path == ("site",)


def test_domain_comment_is_parsed_from_layout(tmp_path: Path) -> None:
    pages = tmp_path / "pages"
    pages.mkdir()
    (pages / "_layout.html").write_text(
        "{# target: body #}\n{# domain: marketing #}\n{% block content %}{% end %}\n",
        encoding="utf-8",
    )
    _write_page(pages)

    routes = discover_pages(pages)
    assert len(routes) == 1
    chain = routes[0].layout_chain
    assert len(chain.layouts) == 1
    assert chain.layouts[0].domain_name == "marketing"
    assert chain.domain_path == ("marketing",)
    assert chain.navigation_domain_path == ("marketing",)


def test_shell_path_inherits_from_ancestor_layouts(tmp_path: Path) -> None:
    pages = tmp_path / "pages"
    showcase = pages / "showcase"
    pages.mkdir()
    showcase.mkdir()
    (pages / "_layout.html").write_text(
        "{# target: body #}\n{# shell: site #}\n{% block content %}{% end %}\n",
        encoding="utf-8",
    )
    (showcase / "_layout.html").write_text(
        "{# target: main #}\n{# shell: showcase #}\n{% block content %}{% end %}\n",
        encoding="utf-8",
    )
    _write_page(showcase)

    routes = discover_pages(pages)
    assert len(routes) == 1
    chain = routes[0].layout_chain
    assert tuple(layout.shell_name for layout in chain.layouts) == ("site", "showcase")
    assert chain.shell_path == ("site", "showcase")
    assert chain.navigation_domain_path == ("site", "showcase")


def test_navigation_domain_path_prefers_explicit_domain_layers(tmp_path: Path) -> None:
    pages = tmp_path / "pages"
    showcase = pages / "showcase"
    pages.mkdir()
    showcase.mkdir()
    (pages / "_layout.html").write_text(
        "{# target: body #}\n{# domain: site #}\n{# shell: site #}\n{% block content %}{% end %}\n",
        encoding="utf-8",
    )
    (showcase / "_layout.html").write_text(
        "{# target: main #}\n{# shell: showcase #}\n{% block content %}{% end %}\n",
        encoding="utf-8",
    )
    _write_page(showcase)

    routes = discover_pages(pages)
    assert len(routes) == 1
    chain = routes[0].layout_chain
    assert chain.domain_path == ("site",)
    assert chain.shell_path == ("site", "showcase")
    assert chain.navigation_domain_path == ("site",)


def test_layout_preset_supplies_metadata_defaults(tmp_path: Path) -> None:
    pages = tmp_path / "pages"
    pages.mkdir()
    (pages / "_layout.html").write_text(
        "{# preset: site-shell #}\n{# domain: site #}\n{# shell: site #}\n{% block content %}{% end %}\n",
        encoding="utf-8",
    )
    _write_page(pages)

    routes = discover_pages(
        pages,
        layout_presets={
            "site-shell": LayoutPreset(
                name="site-shell",
                target="body",
                swap_scope_name="site",
                outlet_target_id="site-content",
                outlet_mode="replace",
            )
        },
    )
    chain = routes[0].layout_chain
    layout = chain.layouts[0]
    assert layout.target == "body"
    assert layout.domain_name == "site"
    assert layout.shell_name == "site"
    assert layout.swap_scope_name == "site"
    assert layout.outlet_target_id == "site-content"
    assert layout.outlet_mode == "replace"


def test_layout_comments_override_preset_defaults(tmp_path: Path) -> None:
    pages = tmp_path / "pages"
    pages.mkdir()
    (pages / "_layout.html").write_text(
        "{# preset: chirpui-app-shell #}\n"
        "{# target: main #}\n"
        "{# domain: showcase #}\n"
        "{# shell: showcase #}\n"
        "{% block content %}{% end %}\n",
        encoding="utf-8",
    )
    _write_page(pages)

    routes = discover_pages(
        pages,
        layout_presets={
            "chirpui-app-shell": LayoutPreset(
                name="chirpui-app-shell",
                target="body",
                swap_scope_name="shell",
                outlet_target_id="main",
            )
        },
    )
    chain = routes[0].layout_chain
    layout = chain.layouts[0]
    assert layout.target == "main"
    assert layout.domain_name == "showcase"
    assert layout.shell_name == "showcase"
    assert layout.swap_scope_name == "shell"
    assert layout.outlet_target_id == "main"


def test_unknown_layout_preset_raises_clear_error(tmp_path: Path) -> None:
    pages = tmp_path / "pages"
    pages.mkdir()
    (pages / "_layout.html").write_text(
        "{# preset: missing #}\n{% block content %}{% end %}\n",
        encoding="utf-8",
    )
    _write_page(pages)

    with pytest.raises(ValueError, match="Unknown layout preset"):
        discover_pages(pages)
