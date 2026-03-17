"""Tests for OOBRegistry — app-level OOB region configuration."""

from pathlib import Path

import pytest
from kida import Environment, FileSystemLoader

from chirp.http.request import Request
from chirp.pages.types import LayoutChain, LayoutInfo
from chirp.templating.composition import PageComposition
from chirp.templating.kida_adapter import KidaAdapter
from chirp.templating.oob_registry import OOBRegionConfig, OOBRegistry
from chirp.server.negotiation_oob import compute_shell_region_updates
from chirp.templating.render_plan import (
    build_layout_contract,
    build_render_plan,
    execute_render_plan,
    serialize_rendered_plan,
)

TEMPLATES_DIR = Path(__file__).parent / "templates"


@pytest.fixture
def kida_env() -> Environment:
    return Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))


def _full_page_request() -> Request:
    async def _receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request.from_asgi(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [],
            "query_string": b"",
            "http_version": "1.1",
            "server": ("127.0.0.1", 8000),
            "client": ("127.0.0.1", 1234),
        },
        receive=_receive,
    )


def _htmx_boosted_request() -> Request:
    async def _receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request.from_asgi(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [
                (b"hx-request", b"true"),
                (b"hx-boosted", b"true"),
            ],
            "query_string": b"",
            "http_version": "1.1",
            "server": ("127.0.0.1", 8000),
            "client": ("127.0.0.1", 1234),
        },
        receive=_receive,
    )


class TestOOBRegionConfig:
    def test_defaults(self) -> None:
        config = OOBRegionConfig(target_id="my-target")
        assert config.target_id == "my-target"
        assert config.swap == "innerHTML"
        assert config.wrap is True

    def test_custom_values(self) -> None:
        config = OOBRegionConfig(target_id="title", swap="true", wrap=False)
        assert config.swap == "true"
        assert config.wrap is False

    def test_frozen(self) -> None:
        config = OOBRegionConfig(target_id="x")
        with pytest.raises(AttributeError):
            config.target_id = "y"  # type: ignore[misc]


class TestOOBRegistry:
    def test_register_and_get(self) -> None:
        reg = OOBRegistry()
        config = OOBRegionConfig(target_id="sidebar-nav")
        reg.register("sidebar_oob", config)
        assert reg.get("sidebar_oob") is config
        assert reg.get("unknown") is None

    def test_freeze_prevents_mutation(self) -> None:
        reg = OOBRegistry()
        reg.freeze()
        with pytest.raises(RuntimeError, match="Cannot modify"):
            reg.register("sidebar_oob", OOBRegionConfig(target_id="x"))

    def test_resolve_target_registered(self) -> None:
        reg = OOBRegistry()
        reg.register("sidebar_oob", OOBRegionConfig(target_id="chirpui-sidebar-nav"))
        assert reg.resolve_target("sidebar_oob") == "chirpui-sidebar-nav"

    def test_resolve_target_convention_fallback(self) -> None:
        reg = OOBRegistry()
        assert reg.resolve_target("sidebar_oob") == "sidebar"
        assert reg.resolve_target("breadcrumbs_oob") == "breadcrumbs"

    def test_resolve_serialization_registered(self) -> None:
        reg = OOBRegistry()
        reg.register("title_oob", OOBRegionConfig(target_id="doc-title", swap="true", wrap=False))
        swap, wrap = reg.resolve_serialization("doc-title")
        assert swap == "true"
        assert wrap is False

    def test_resolve_serialization_fallback(self) -> None:
        reg = OOBRegistry()
        swap, wrap = reg.resolve_serialization("unknown-target")
        assert swap == "true"
        assert wrap is True

    def test_registered_blocks(self) -> None:
        reg = OOBRegistry()
        reg.register("a_oob", OOBRegionConfig(target_id="a"))
        reg.register("b_oob", OOBRegionConfig(target_id="b"))
        assert reg.registered_blocks == frozenset({"a_oob", "b_oob"})

    def test_contract_cache_scoped_to_instance(self, kida_env: Environment) -> None:
        reg1 = OOBRegistry()
        reg1.register("sidebar_oob", OOBRegionConfig(target_id="s1"))
        reg2 = OOBRegistry()
        reg2.register("sidebar_oob", OOBRegionConfig(target_id="s2"))

        adapter = KidaAdapter(kida_env)
        c1 = reg1.get_or_build_contract(adapter, "oob_layout/_layout.html")
        c2 = reg2.get_or_build_contract(adapter, "oob_layout/_layout.html")

        t1 = {b.block_name: b.target_id for b in c1.oob_blocks}
        t2 = {b.block_name: b.target_id for b in c2.oob_blocks}
        assert t1.get("sidebar_oob") == "s1"
        assert t2.get("sidebar_oob") == "s2"


class TestBuildLayoutContractWithRegistry:
    def test_registry_resolves_target_id(self, kida_env: Environment) -> None:
        reg = OOBRegistry()
        reg.register("sidebar_oob", OOBRegionConfig(target_id="custom-sidebar"))
        adapter = KidaAdapter(kida_env)
        contract = build_layout_contract(
            adapter,
            "oob_layout/_layout.html",
            oob_registry=reg,
        )
        targets = {b.block_name: b.target_id for b in contract.oob_blocks}
        assert targets["sidebar_oob"] == "custom-sidebar"

    def test_without_registry_uses_convention(self, kida_env: Environment) -> None:
        adapter = KidaAdapter(kida_env)
        contract = build_layout_contract(adapter, "oob_layout/_layout.html")
        targets = {b.block_name: b.target_id for b in contract.oob_blocks}
        assert targets["sidebar_oob"] == "sidebar"


class TestSerializeWithRegistry:
    def test_custom_swap_and_wrap(self) -> None:
        from chirp.templating.render_plan import RenderedPlan

        reg = OOBRegistry()
        reg.register(
            "title_oob",
            OOBRegionConfig(
                target_id="doc-title",
                swap="true",
                wrap=False,
            ),
        )
        reg.register(
            "sidebar_oob",
            OOBRegionConfig(
                target_id="sidebar-nav",
                swap="innerHTML",
                wrap=True,
            ),
        )

        rendered = RenderedPlan(
            main_html="<main>content</main>",
            region_htmls={
                "doc-title": "<title>Page</title>",
                "sidebar-nav": "<ul><li>Nav</li></ul>",
            },
        )
        html = serialize_rendered_plan(rendered, oob_registry=reg)

        assert "<title>Page</title>" in html
        assert '<div id="doc-title"' not in html
        assert '<div id="sidebar-nav" hx-swap-oob="innerHTML">' in html

    def test_unregistered_target_gets_outerhtml_default(self) -> None:
        from chirp.templating.render_plan import RenderedPlan

        reg = OOBRegistry()
        rendered = RenderedPlan(
            main_html="<main/>",
            region_htmls={"unknown-region": "<p>hi</p>"},
        )
        html = serialize_rendered_plan(rendered, oob_registry=reg)
        assert 'hx-swap-oob="true"' in html
        assert '<div id="unknown-region"' in html


class TestFullPipelineWithRegistry:
    def test_custom_oob_region_in_full_pipeline(self, kida_env: Environment) -> None:
        """Registry-configured regions flow through execute -> serialize correctly."""
        reg = OOBRegistry()
        reg.register(
            "sidebar_oob",
            OOBRegionConfig(
                target_id="custom-sidebar",
                swap="innerHTML",
            ),
        )

        adapter = KidaAdapter(kida_env)
        layout_chain = LayoutChain(
            layouts=(LayoutInfo(template_name="oob_layout/_layout.html", target="body", depth=0),)
        )
        comp = PageComposition(
            template="oob_layout/page.html",
            fragment_block="content",
            page_block="content",
            context={},
            layout_chain=layout_chain,
        )
        req = _htmx_boosted_request()
        shell_updates = compute_shell_region_updates(comp, req, None)
        plan = build_render_plan(comp, request=req, shell_region_updates=shell_updates)
        rendered = execute_render_plan(plan, adapter=adapter, oob_registry=reg)
        html = serialize_rendered_plan(rendered, oob_registry=reg)

        assert "hx-swap-oob" in html
        if "custom-sidebar" in rendered.region_htmls:
            assert 'id="custom-sidebar"' in html
            assert 'hx-swap-oob="innerHTML"' in html
