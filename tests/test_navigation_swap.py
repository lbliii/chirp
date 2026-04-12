"""Tests for route-aware navigation swap resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from chirp import App, AppConfig
from chirp.pages.types import LayoutChain, LayoutInfo
from chirp.templating.fragment_target_registry import FragmentTargetRegistry
from chirp.templating.navigation_swap import make_swap_attrs, resolve_navigation_swap
from chirp.testing.client import TestClient


def test_swap_attrs_returns_empty_without_request_context() -> None:
    """swap_attrs must not raise when called outside a request context."""
    fn = make_swap_attrs(
        route_layout_chains={},
        router=None,
        fragment_target_registry=FragmentTargetRegistry(),
        swap_scope_map={},
    )
    assert fn("/some-path") == {}


def test_resolve_navigation_swap_targets_last_shared_shell_ancestor() -> None:
    registry = FragmentTargetRegistry()
    registry.register("site-content", fragment_block="content", scope_name="site")
    registry.register("main", fragment_block="page_root", scope_name="section")
    registry.freeze()

    current = LayoutChain(
        layouts=(
            LayoutInfo(
                "pages/_layout.html",
                "body",
                0,
                shell_name="site",
                swap_scope_name="site",
                outlet_target_id="site-content",
            ),
        )
    )
    dest = LayoutChain(
        layouts=(
            LayoutInfo(
                "pages/_layout.html",
                "body",
                0,
                shell_name="site",
                swap_scope_name="site",
                outlet_target_id="site-content",
            ),
            LayoutInfo(
                "pages/showcase/_layout.html",
                "main",
                1,
                shell_name="showcase",
                swap_scope_name="section",
            ),
        )
    )

    res = resolve_navigation_swap(
        current_path="/",
        destination_path="/showcase",
        layout_chain_current=current,
        layout_chain_dest=dest,
        registry=registry,
        swap_scope_map={"site": "site-content", "section": "main"},
    )

    assert res is not None
    assert res.htmx_target == "#site-content"
    assert res.scope == "site"


def test_resolve_navigation_swap_targets_nearest_shared_nested_shell() -> None:
    registry = FragmentTargetRegistry()
    registry.register("site-content", fragment_block="content", scope_name="site")
    registry.register("community-content", fragment_block="content", scope_name="community")
    registry.register("main", fragment_block="page_root", scope_name="section")
    registry.freeze()

    current = LayoutChain(
        layouts=(
            LayoutInfo(
                "pages/_layout.html",
                "body",
                0,
                shell_name="site",
                swap_scope_name="site",
                outlet_target_id="site-content",
            ),
            LayoutInfo(
                "pages/community/_layout.html",
                "site-content",
                1,
                shell_name="community",
                swap_scope_name="community",
                outlet_target_id="community-content",
            ),
            LayoutInfo(
                "pages/community/python/_layout.html",
                "community-content",
                2,
                shell_name="python",
                swap_scope_name="section",
                outlet_target_id="main",
            ),
        )
    )
    dest = LayoutChain(
        layouts=(
            LayoutInfo(
                "pages/_layout.html",
                "body",
                0,
                shell_name="site",
                swap_scope_name="site",
                outlet_target_id="site-content",
            ),
            LayoutInfo(
                "pages/community/_layout.html",
                "site-content",
                1,
                shell_name="community",
                swap_scope_name="community",
                outlet_target_id="community-content",
            ),
            LayoutInfo(
                "pages/community/javascript/_layout.html",
                "community-content",
                2,
                shell_name="javascript",
                swap_scope_name="section",
                outlet_target_id="main",
            ),
        )
    )

    res = resolve_navigation_swap(
        current_path="/community/python",
        destination_path="/community/javascript",
        layout_chain_current=current,
        layout_chain_dest=dest,
        registry=registry,
        swap_scope_map={
            "site": "site-content",
            "community": "community-content",
            "section": "main",
        },
    )

    assert res is not None
    assert res.htmx_target == "#community-content"
    assert res.scope == "community"


def test_resolve_navigation_swap_prefers_explicit_domains_over_shell_metadata() -> None:
    registry = FragmentTargetRegistry()
    registry.register("site-content", fragment_block="content", scope_name="site")
    registry.register("main", fragment_block="page_root", scope_name="section")
    registry.freeze()

    current = LayoutChain(
        layouts=(
            LayoutInfo(
                "pages/_layout.html",
                "body",
                0,
                domain_name="site",
                swap_scope_name="site",
                outlet_target_id="site-content",
            ),
        )
    )
    dest = LayoutChain(
        layouts=(
            LayoutInfo(
                "pages/_layout.html",
                "body",
                0,
                domain_name="site",
                swap_scope_name="site",
                outlet_target_id="site-content",
            ),
            LayoutInfo(
                "pages/showcase/_layout.html",
                "main",
                1,
                domain_name="showcase",
                shell_name="showcase-shell",
                swap_scope_name="section",
            ),
        )
    )

    res = resolve_navigation_swap(
        current_path="/",
        destination_path="/showcase",
        layout_chain_current=current,
        layout_chain_dest=dest,
        registry=registry,
        swap_scope_map={"site": "site-content", "section": "main"},
    )

    assert res is not None
    assert res.htmx_target == "#site-content"
    assert res.scope == "site"


def test_resolve_navigation_swap_returns_none_without_shared_shell_ancestor() -> None:
    registry = FragmentTargetRegistry()
    registry.register("site-content", fragment_block="content", scope_name="site")
    registry.register("admin-content", fragment_block="content", scope_name="admin")
    registry.freeze()

    current = LayoutChain(
        layouts=(
            LayoutInfo(
                "pages/_layout.html",
                "body",
                0,
                shell_name="site",
                swap_scope_name="site",
                outlet_target_id="site-content",
            ),
        )
    )
    dest = LayoutChain(
        layouts=(
            LayoutInfo(
                "pages/admin/_layout.html",
                "body",
                0,
                shell_name="admin",
                swap_scope_name="admin",
                outlet_target_id="admin-content",
            ),
        )
    )

    assert (
        resolve_navigation_swap(
            current_path="/",
            destination_path="/admin",
            layout_chain_current=current,
            layout_chain_dest=dest,
            registry=registry,
            swap_scope_map={"site": "site-content", "admin": "admin-content"},
        )
        is None
    )


def test_resolve_navigation_swap_keeps_legacy_behavior_without_shell_annotations() -> None:
    registry = FragmentTargetRegistry()
    registry.register("site-content", fragment_block="content", scope_name="site")
    registry.freeze()

    chain = LayoutChain(
        layouts=(
            LayoutInfo(
                "pages/_layout.html",
                "body",
                0,
                swap_scope_name="site",
                outlet_target_id="site-content",
            ),
        )
    )

    res = resolve_navigation_swap(
        current_path="/",
        destination_path="/contact",
        layout_chain_current=chain,
        layout_chain_dest=chain,
        registry=registry,
        swap_scope_map={"site": "site-content"},
    )

    assert res is not None
    assert res.htmx_target == "#site-content"
    assert res.scope == "site"


@pytest.mark.asyncio
async def test_streamed_suspense_layout_preserves_request_context_for_swap_attrs(
    tmp_path: Path,
) -> None:
    pages = tmp_path / "pages"
    showcase = pages / "showcase"
    pages.mkdir()
    showcase.mkdir()

    (pages / "_layout.html").write_text(
        '{# target: body #}\n'
        '{# swap_scope: site #}\n'
        '{# outlet: site-content #}\n'
        '<a id="showcase-link" href="/showcase" {{ swap_attrs("/showcase") | html_attrs }}>Showcase</a>\n'
        '<div id="site-content">{% block content %}{% end %}</div>\n',
        encoding="utf-8",
    )
    (pages / "page.html").write_text(
        '<div id="page-root">\n'
        "<h1>{{ title }}</h1>\n"
        '<div id="data">{% block data %}{% if data %}{{ data }}{% else %}Loading...{% end %}{% end %}</div>\n'
        "</div>\n",
        encoding="utf-8",
    )
    (pages / "page.py").write_text(
        "import asyncio\n\n"
        "from chirp import Suspense\n\n"
        "async def _data() -> str:\n"
        "    await asyncio.sleep(0)\n"
        "    return 'ready'\n\n"
        "def get() -> Suspense:\n"
        "    return Suspense('page.html', title='Home', data=_data())\n",
        encoding="utf-8",
    )
    (showcase / "page.html").write_text(
        '<div id="page-root"><h1>{{ title }}</h1></div>\n',
        encoding="utf-8",
    )
    (showcase / "page.py").write_text(
        "def get() -> dict[str, str]:\n"
        "    return {'title': 'Showcase'}\n",
        encoding="utf-8",
    )

    app = App(AppConfig(template_dir=pages, secret_key="test"))
    app.register_swap_scope("site", "site-content")
    app.register_fragment_target("site-content", fragment_block="content", scope_name="site")
    app.mount_pages(str(pages))

    async with TestClient(app) as client:
        response = await client.get("/")

    assert 'id="showcase-link"' in response.text
    assert 'hx-target="#site-content"' in response.text
    assert 'hx-boost="true"' in response.text
