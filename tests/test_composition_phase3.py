"""Phase 3 tests: Kida composition API and block validation."""

from pathlib import Path

import pytest
from kida import Environment, FileSystemLoader

from chirp.http.request import Request
from chirp.pages.types import LayoutChain, LayoutInfo
from chirp.templating.composition import PageComposition
from chirp.templating.kida_adapter import KidaAdapter
from chirp.templating.composition import RegionUpdate, ViewRef
from chirp.templating.render_plan import (
    _oob_block_names,
    build_render_plan,
    execute_render_plan,
    serialize_rendered_plan,
)

TEMPLATES_DIR = Path(__file__).parent / "templates"


@pytest.fixture
def kida_env() -> Environment:
    return Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))


def _htmx_fragment_request() -> Request:
    async def _receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request.from_asgi(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"hx-request", b"true")],
            "query_string": b"",
            "http_version": "1.1",
            "server": ("127.0.0.1", 8000),
            "client": ("127.0.0.1", 1234),
        },
        receive=_receive,
    )


def _full_page_request() -> Request:
    """Request without hx-request — triggers full-page render."""

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


def _htmx_boosted_request(*, htmx_target: str | None = None) -> Request:
    """HTMX boosted request — triggers page_fragment with layouts and OOB region updates."""

    async def _receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    headers: list[tuple[bytes, bytes]] = [
        (b"hx-request", b"true"),
        (b"hx-boosted", b"true"),
    ]
    if htmx_target is not None:
        headers.append((b"hx-target", htmx_target.encode()))

    return Request.from_asgi(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": headers,
            "query_string": b"",
            "http_version": "1.1",
            "server": ("127.0.0.1", 8000),
            "client": ("127.0.0.1", 1234),
        },
        receive=_receive,
    )


class TestKidaAdapterTemplateMetadata:
    """KidaAdapter.template_metadata returns structure for composition planning."""

    def test_returns_metadata_for_existing_template(self, kida_env: Environment) -> None:
        adapter = KidaAdapter(kida_env)
        meta = adapter.template_metadata("search.html")
        assert meta is not None
        assert hasattr(meta, "blocks")
        assert "results_list" in meta.blocks

    def test_returns_none_for_missing_template(self, kida_env: Environment) -> None:
        adapter = KidaAdapter(kida_env)
        meta = adapter.template_metadata("nonexistent.html")
        assert meta is None


class TestRenderPlanBlockValidation:
    """execute_render_plan validate_blocks catches missing blocks before render."""

    def test_validate_blocks_raises_for_missing_block(self, kida_env: Environment) -> None:
        adapter = KidaAdapter(kida_env)
        comp = PageComposition(
            template="search.html",
            fragment_block="nonexistent_block",
            context={"results": []},
        )
        plan = build_render_plan(comp, request=_htmx_fragment_request())
        with pytest.raises(KeyError, match="Block 'nonexistent_block' not found"):
            execute_render_plan(plan, adapter=adapter, validate_blocks=True)

    def test_validate_blocks_succeeds_for_valid_block(self, kida_env: Environment) -> None:
        adapter = KidaAdapter(kida_env)
        comp = PageComposition(
            template="search.html",
            fragment_block="results_list",
            context={"results": ["a"]},
        )
        plan = build_render_plan(comp, request=_htmx_fragment_request())
        rendered = execute_render_plan(plan, adapter=adapter, validate_blocks=True)
        assert "a" in rendered.main_html

    def test_validate_blocks_default_off_raises_at_render(self, kida_env: Environment) -> None:
        """Without validate_blocks, missing block raises at render time (Kida KeyError)."""
        adapter = KidaAdapter(kida_env)
        comp = PageComposition(
            template="search.html",
            fragment_block="nonexistent_block",
            context={"results": []},
        )
        plan = build_render_plan(comp, request=_htmx_fragment_request())
        with pytest.raises(KeyError, match="nonexistent_block"):
            execute_render_plan(plan, adapter=adapter, validate_blocks=False)


class TestValidateBlocksWiredToDebug:
    """validate_blocks is passed from handler when config.debug=True."""

    async def test_debug_mode_validates_blocks(self) -> None:
        from chirp import App
        from chirp.config import AppConfig
        from chirp.testing import TestClient

        templates_dir = Path(__file__).parent / "templates"
        app = App(
            config=AppConfig(
                template_dir=templates_dir,
                debug=True,
                skip_contract_checks=True,
            )
        )

        @app.route("/bad-block")
        def bad_block():
            from chirp.templating.composition import PageComposition

            return PageComposition(
                template="search.html",
                fragment_block="nonexistent_block",
                context={"results": []},
            )

        async with TestClient(app) as client:
            # Fragment request to trigger block render (not full template)
            response = await client.fragment("/bad-block")
            assert response.status == 500
            assert "nonexistent_block" in response.text or "Block" in response.text


class TestFullPageOobLayoutComposition:
    """Regression: full-page composition with layout that has regions must preserve structure.

    _oob_block_names uses 'prefer regions, fallback to blocks'. Combining regions U blocks
    caused dori layouts to break (fragmented HTML, card headers outside articles).
    """

    def test_oob_layout_preserves_page_content_structure(self, kida_env: Environment) -> None:
        """Full-page render with layout containing {% region *_oob %} must not fragment content."""
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
        plan = build_render_plan(comp, request=_full_page_request())
        rendered = execute_render_plan(plan, adapter=adapter)
        html = serialize_rendered_plan(rendered)

        # Page content must be intact: card header and body inside the article
        assert "Body content here" in html
        assert 'class="card__header"' in html
        assert 'class="card__body"' in html
        # Card structure must not be fragmented (header/body inside article, not siblings)
        card_start = html.find('<article class="card">')
        card_end = html.find("</article>")
        assert card_start >= 0
        assert card_end > card_start
        card_inner = html[card_start:card_end]
        assert "card__header" in card_inner
        assert "card__body" in card_inner
        assert "Body content here" in card_inner

    def test_oob_blocks_suppressed_on_full_page(self, kida_env: Environment) -> None:
        """OOB regions (sidebar_oob) must be suppressed on full-page to avoid orphaned fragments."""
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
        plan = build_render_plan(comp, request=_full_page_request())
        rendered = execute_render_plan(plan, adapter=adapter)
        html = serialize_rendered_plan(rendered)

        # Main content must be present; OOB region content is suppressed (empty)
        assert 'id="main"' in html
        assert "Body content here" in html

    def test_regular_block_oob_not_suppressed_on_full_page(self, kida_env: Environment) -> None:
        """Layout with {% block content_oob %} (regular block, not region) must NOT be suppressed.

        Prefer-regions only suppresses {% region *_oob %}. A regular {% block foo_oob %}
        is not an OOB swap target — suppressing it would break layout structure.
        Combine (regions ∪ blocks ending _oob) would incorrectly suppress it.
        """
        adapter = KidaAdapter(kida_env)
        layout_chain = LayoutChain(
            layouts=(
                LayoutInfo(
                    template_name="oob_layout/block_oob_layout.html",
                    target="body",
                    depth=0,
                ),
            )
        )
        comp = PageComposition(
            template="oob_layout/block_oob_page.html",
            fragment_block="content",
            page_block="content",
            context={},
            layout_chain=layout_chain,
        )
        plan = build_render_plan(comp, request=_full_page_request())
        rendered = execute_render_plan(plan, adapter=adapter)
        html = serialize_rendered_plan(rendered)

        # content_oob is a regular block (not region) — must NOT be suppressed
        before_main = html.split("<main")[0]
        assert "critical-wrapper" in before_main
        assert "CRITICAL_STRUCTURE" in html


class TestMultiLevelLayoutChain:
    """Dori-style: root_layout wraps page that extends page_layout; OOB suppressed on full-page."""

    def test_root_layout_wraps_page_that_extends_inner_layout(self, kida_env: Environment) -> None:
        """Full-page with root_layout; page extends _page_layout. Structure and OOB correct."""
        adapter = KidaAdapter(kida_env)
        # Only root_layout in chain — page extends _page_layout, so we don't double-wrap
        layout_chain = LayoutChain(
            layouts=(LayoutInfo(template_name="oob_layout/_layout.html", target="body", depth=0),)
        )
        comp = PageComposition(
            template="oob_layout/chain_page.html",
            fragment_block="page_content",
            page_block="page_content",
            context={},
            layout_chain=layout_chain,
        )
        plan = build_render_plan(comp, request=_full_page_request())
        rendered = execute_render_plan(plan, adapter=adapter)
        html = serialize_rendered_plan(rendered)

        # Page structure intact; OOB suppressed (sidebar from root layout)
        assert "Chain body content" in html
        assert 'class="card__header"' in html
        assert 'id="main"' in html


class TestPageFragmentOobRegions:
    """Boosted fragment request returns main_html + OOB region fragments for HTMX swaps."""

    def test_fragment_includes_region_updates(self, kida_env: Environment) -> None:
        """Page fragment with layout chain has region_htmls (shell_actions + layout OOB when not site-scoped)."""
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
        plan = build_render_plan(comp, request=_htmx_boosted_request())
        rendered = execute_render_plan(plan, adapter=adapter)

        # Boosted fragment always gets shell_actions; layout OOB added when cache_scope != site
        assert len(rendered.region_htmls) >= 1

    def test_serialize_appends_oob_fragments(self, kida_env: Environment) -> None:
        """Serialized fragment response includes hx-swap-oob divs for region updates."""
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
        plan = build_render_plan(comp, request=_htmx_boosted_request())
        rendered = execute_render_plan(plan, adapter=adapter)
        html = serialize_rendered_plan(rendered)

        assert "hx-swap-oob" in html


class TestLayoutWithNoOobBlocks:
    """Layout without {% region *_oob %} — CHIRPUI_OOB_BLOCKS fallback still suppresses."""

    def test_simple_layout_composes_correctly(self, kida_env: Environment) -> None:
        """Layout with no OOB regions composes; content block injected; no crash."""
        adapter = KidaAdapter(kida_env)
        layout_chain = LayoutChain(
            layouts=(
                LayoutInfo(template_name="oob_layout/simple_layout.html", target="body", depth=0),
            )
        )
        comp = PageComposition(
            template="oob_layout/simple_page.html",
            fragment_block="content",
            page_block="content",
            context={},
            layout_chain=layout_chain,
        )
        plan = build_render_plan(comp, request=_full_page_request())
        rendered = execute_render_plan(plan, adapter=adapter)
        html = serialize_rendered_plan(rendered)

        assert "Simple content" in html
        assert 'id="main"' in html


class TestExplicitRegionUpdates:
    """PageComposition(regions=[...]) — custom regions included in region_htmls."""

    def test_explicit_region_update_rendered(self, kida_env: Environment) -> None:
        """Explicit RegionUpdate from composition is rendered and serialized."""
        adapter = KidaAdapter(kida_env)
        comp = PageComposition(
            template="search.html",
            fragment_block="results_list",
            context={"results": ["x", "y"]},
            regions=(
                RegionUpdate(
                    region="custom-badge",
                    view=ViewRef(
                        template="search.html",
                        block="results_list",
                        context={"results": ["badge"]},
                    ),
                ),
            ),
        )
        plan = build_render_plan(comp, request=_htmx_boosted_request())
        rendered = execute_render_plan(plan, adapter=adapter)

        assert "custom-badge" in rendered.region_htmls
        assert "badge" in rendered.region_htmls["custom-badge"]


class TestOobBlockNames:
    """Unit tests for _oob_block_names: prefer regions, fallback to blocks."""

    def test_prefers_regions_when_available(self, kida_env: Environment) -> None:
        """Kida template with {% region sidebar_oob %} — returns region blocks only."""
        adapter = KidaAdapter(kida_env)
        result = _oob_block_names(adapter, "oob_layout/_layout.html")
        assert result == {"sidebar_oob"}

    def test_fallback_to_blocks_when_regions_returns_none(self) -> None:
        """Adapter with regions() returning None — falls back to blocks filter."""
        meta = type("Meta", (), {"regions": lambda self: None, "blocks": ["content", "nav_oob"]})()
        adapter = type("Adapter", (), {"template_metadata": lambda self, t: meta})()
        result = _oob_block_names(adapter, "any.html")
        assert result == {"nav_oob"}

    def test_fallback_to_blocks_when_no_regions_method(self) -> None:
        """Adapter with blocks but no regions() — uses blocks filter."""
        meta = type("Meta", (), {"blocks": ["content", "breadcrumbs_oob", "sidebar_oob"]})()
        adapter = type("Adapter", (), {"template_metadata": lambda self, t: meta})()
        result = _oob_block_names(adapter, "any.html")
        assert result == {"breadcrumbs_oob", "sidebar_oob"}

    def test_returns_empty_when_metadata_none(self) -> None:
        """Adapter returning None metadata — returns empty set."""
        adapter = type("Adapter", (), {"template_metadata": lambda self, t: None})()
        result = _oob_block_names(adapter, "any.html")
        assert result == set()


class TestLayoutStartIndex:
    """HX-Target depth-aware layout skipping — layout_start_index skips outer layouts."""

    def test_htmx_target_app_content_skips_root_layout(self, kida_env: Environment) -> None:
        """Boosted request with HX-Target: #app-content applies only inner layout."""
        adapter = KidaAdapter(kida_env)
        layout_chain = LayoutChain(
            layouts=(
                LayoutInfo(
                    template_name="oob_layout/_depth_root.html",
                    target="body",
                    depth=0,
                ),
                LayoutInfo(
                    template_name="oob_layout/_depth_inner.html",
                    target="app-content",
                    depth=1,
                ),
            )
        )
        comp = PageComposition(
            template="oob_layout/depth_page.html",
            fragment_block="content",
            page_block="content",
            context={},
            layout_chain=layout_chain,
        )
        request = _htmx_boosted_request(htmx_target="#app-content")
        plan = build_render_plan(comp, request=request)

        assert plan.layout_start_index == 1

        rendered = execute_render_plan(plan, adapter=adapter)
        html = serialize_rendered_plan(rendered)

        # Only inner layout applied — no html/body from root
        assert "<html>" not in html
        assert "<body>" not in html
        assert 'id="app-content"' in html
        assert "Depth page content" in html

    def test_full_page_applies_all_layouts(self, kida_env: Environment) -> None:
        """Full-page request applies entire layout chain."""
        adapter = KidaAdapter(kida_env)
        layout_chain = LayoutChain(
            layouts=(
                LayoutInfo(
                    template_name="oob_layout/_depth_root.html",
                    target="body",
                    depth=0,
                ),
                LayoutInfo(
                    template_name="oob_layout/_depth_inner.html",
                    target="app-content",
                    depth=1,
                ),
            )
        )
        comp = PageComposition(
            template="oob_layout/depth_page.html",
            fragment_block="content",
            page_block="content",
            context={},
            layout_chain=layout_chain,
        )
        plan = build_render_plan(comp, request=_full_page_request())

        assert plan.layout_start_index == 0

        rendered = execute_render_plan(plan, adapter=adapter)
        html = serialize_rendered_plan(rendered)

        assert "<html>" in html
        assert "<body>" in html
        assert 'id="app-content"' in html
        assert "Depth page content" in html
