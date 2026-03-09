"""Phase 3 tests: Kida composition API and block validation."""

from pathlib import Path

import pytest
from kida import Environment, FileSystemLoader

from chirp.http.request import Request
from chirp.pages.types import LayoutChain, LayoutInfo
from chirp.templating.composition import PageComposition
from chirp.templating.kida_adapter import KidaAdapter
from chirp.templating.render_plan import (
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

    _oob_block_names uses 'prefer regions, fallback to blocks'. Combining regions ∪ blocks
    caused dori layouts to break (fragmented HTML, card headers outside articles).
    """

    def test_oob_layout_preserves_page_content_structure(self, kida_env: Environment) -> None:
        """Full-page render with layout containing {% region *_oob %} must not fragment content."""
        adapter = KidaAdapter(kida_env)
        layout_chain = LayoutChain(
            layouts=(
                LayoutInfo(template_name="oob_layout/_layout.html", target="body", depth=0),
            )
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
        assert card_start >= 0 and card_end > card_start
        card_inner = html[card_start:card_end]
        assert "card__header" in card_inner
        assert "card__body" in card_inner
        assert "Body content here" in card_inner

    def test_oob_blocks_suppressed_on_full_page(self, kida_env: Environment) -> None:
        """OOB regions (sidebar_oob) must be suppressed on full-page to avoid orphaned fragments."""
        adapter = KidaAdapter(kida_env)
        layout_chain = LayoutChain(
            layouts=(
                LayoutInfo(template_name="oob_layout/_layout.html", target="body", depth=0),
            )
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
