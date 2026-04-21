"""Integration smoke tests for kida's native ``{% fragment %}`` directive.

Kida 0.6.0+ ships ``{% fragment name %}...{% end %}`` as a Block AST node
with ``fragment=True``. During full-template render the body is suppressed;
``render_block`` renders it like any other block. Chirp must recognise these
as valid swap-only targets everywhere a regular ``{% block %}`` works —
``render_fragment``, the OOB registry, and every contract rule that walks
``block_metadata()``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from kida import DictLoader, Environment

from chirp import App, AppConfig
from chirp.contracts import check_hypermedia_surface
from chirp.contracts.rules_unreachable_blocks import check_unreachable_blocks
from chirp.errors import BlockNotFoundError
from chirp.templating.fragment_target_registry import PageShellContract, PageShellTarget
from chirp.templating.integration import render_fragment
from chirp.templating.returns import Fragment, Template
from chirp.testing import TestClient
from tests.helpers.contract_fixtures import write_layout_page


def _env(templates: dict[str, str]) -> Environment:
    return Environment(loader=DictLoader(templates))


class TestWhitespaceContract:
    """A ``{% fragment %}`` block emits *exactly* zero characters at root render."""

    def test_body_fully_suppressed(self) -> None:
        env = _env({"t.html": "BEFORE{%- fragment only_swap -%}<div>HELLO</div>{%- end -%}AFTER"})
        tpl = env.get_template("t.html")
        assert tpl.render() == "BEFOREAFTER"

    def test_zero_output_when_fragment_is_sole_content(self) -> None:
        """With stripping markers, an all-fragment template renders to empty string."""
        env = _env({"t.html": "{%- fragment only_swap -%}<div>HI</div>{%- end -%}"})
        tpl = env.get_template("t.html")
        assert tpl.render() == ""


class TestRenderBlockResolution:
    """``render_block`` / ``render_fragment`` render fragment blocks like regular blocks."""

    def test_render_block_returns_body(self) -> None:
        env = _env({"t.html": "{% fragment only_swap %}<div>{{ name }}</div>{% end %}"})
        tpl = env.get_template("t.html")
        assert tpl.render_block("only_swap", {"name": "alice"}) == "<div>alice</div>"

    def test_list_blocks_surfaces_fragment_blocks(self) -> None:
        env = _env({"t.html": ("{% fragment swap_only %}x{% end %}{% block regular %}y{% end %}")})
        tpl = env.get_template("t.html")
        assert set(tpl.list_blocks()) == {"swap_only", "regular"}

    def test_block_metadata_surfaces_fragment_blocks(self) -> None:
        env = _env({"t.html": ("{% fragment swap_only %}x{% end %}{% block regular %}y{% end %}")})
        tpl = env.get_template("t.html")
        metadata = tpl.block_metadata()
        assert set(metadata) == {"swap_only", "regular"}

    def test_render_fragment_helper_resolves(self) -> None:
        env = _env({"t.html": "{% fragment swap_only %}<li>{{ v }}</li>{% end %}"})
        out = render_fragment(env, Fragment("t.html", "swap_only", v="42"))
        assert out == "<li>42</li>"

    def test_render_fragment_missing_block_raises_blocknotfound(self) -> None:
        env = _env({"t.html": "{% fragment present %}x{% end %}"})
        with pytest.raises(BlockNotFoundError) as exc_info:
            render_fragment(
                env,
                Fragment(
                    "t.html",
                    "typo",
                ),
            )
        assert exc_info.value.template == "t.html"
        assert exc_info.value.block == "typo"


class TestAppIntegration:
    """End-to-end: ``Fragment("tpl.html", "name", ...)`` resolves a kida fragment block."""

    @pytest.fixture
    def app_with_fragment_block(self, tmp_path: Path) -> App:
        tmpl_dir = tmp_path / "templates"
        tmpl_dir.mkdir()
        (tmpl_dir / "page.html").write_text(
            "<!doctype html><html><body>\n"
            "{% block main %}<p>main: {{ name }}</p>{% end %}\n"
            '{% fragment success_panel %}<div class="ok">saved {{ name }}</div>{% end %}\n'
            "</body></html>\n"
        )
        app = App(config=AppConfig(template_dir=str(tmpl_dir), debug=False))

        @app.route("/page/{name}")
        def page(name: str):
            return Template("page.html", name=name)

        @app.route("/save/{name}", methods=["POST"])
        def save(name: str):
            return Fragment("page.html", "success_panel", name=name)

        return app

    async def test_full_render_omits_fragment_body(self, app_with_fragment_block: App) -> None:
        async with TestClient(app_with_fragment_block) as client:
            response = await client.get("/page/alice")
        assert response.status == 200
        assert "main: alice" in response.text
        # Fragment body must not leak into the full page.
        assert 'class="ok"' not in response.text
        assert "saved alice" not in response.text

    async def test_fragment_handler_renders_fragment_block(
        self, app_with_fragment_block: App
    ) -> None:
        async with TestClient(app_with_fragment_block) as client:
            response = await client.post("/save/bob")
        assert response.status == 200
        assert response.text.strip() == '<div class="ok">saved bob</div>'

    async def test_frag_dispatch_resolves_fragment_block(
        self, app_with_fragment_block: App
    ) -> None:
        """The ``/_frag{path}?_b=...`` dispatcher should address fragment blocks."""
        async with TestClient(app_with_fragment_block) as client:
            response = await client.get("/_frag/page/carol?_b=success_panel")
        assert response.status == 200
        assert response.text.strip() == '<div class="ok">saved carol</div>'


class TestUnreachableBlocksSkipsFragments:
    """The unreachable-block check must not flag ``{% fragment %}`` blocks."""

    def test_fragment_block_siblings_are_not_flagged(self) -> None:
        env = _env(
            {
                "page.html": (
                    "{% block page_root %}{% block page_content %}x{% end %}{% end %}"
                    "{% fragment only_swap %}<div>y</div>{% end %}"
                )
            }
        )
        assert check_unreachable_blocks({"page.html"}, env) == []

    def test_regular_sibling_still_flagged_alongside_fragment(self) -> None:
        """Sanity: the rule still catches real unreachable blocks when a fragment coexists."""
        env = _env(
            {
                "page.html": (
                    "{% block page_root %}{% block page_content %}x{% end %}{% end %}"
                    "{% block page_scripts %}<script></script>{% end %}"
                    "{% fragment only_swap %}y{% end %}"
                )
            }
        )
        issues = check_unreachable_blocks({"page.html"}, env)
        assert len(issues) == 1
        assert "page_scripts" in issues[0].message
        assert "only_swap" not in issues[0].message


class TestFragmentTargetRegistryWithFragmentBlock:
    """Fragment target registry treats fragment blocks identically to ``{% block %}``."""

    def _app(self, tmp_path: Path, page_body: str) -> App:
        write_layout_page(
            tmp_path,
            "<html><body>{% block content %}{% endblock %}</body></html>",
            f'{{% extends "_layout.html" %}}{{% block content %}}{page_body}{{% endblock %}}',
        )
        app = App(AppConfig(template_dir=str(tmp_path)))

        @app.route("/")
        def index():
            return "ok"

        app._mutable_state.page_leaf_templates.add("page.html")
        app._mutable_state.page_templates.add("page.html")
        return app

    def test_fragment_block_satisfies_required_target(self, tmp_path: Path) -> None:
        app = self._app(tmp_path, "{% fragment swap_only %}hi{% end %}")
        app._mutable_state.fragment_target_registry.register(
            "page-root", fragment_block="swap_only", required=True
        )
        result = check_hypermedia_surface(app)
        orphans = [i for i in result.issues if i.category == "fragment_target_orphan"]
        assert orphans == []

    def test_missing_fragment_block_is_orphan_error(self, tmp_path: Path) -> None:
        app = self._app(tmp_path, "{% fragment swap_only %}hi{% end %}")
        app._mutable_state.fragment_target_registry.register(
            "page-root", fragment_block="does_not_exist", required=True
        )
        result = check_hypermedia_surface(app)
        orphans = [i for i in result.issues if i.category == "fragment_target_orphan"]
        assert len(orphans) == 1
        assert orphans[0].severity.name == "ERROR"

    def test_page_shell_contract_accepts_fragment_block(self, tmp_path: Path) -> None:
        app = self._app(tmp_path, "{% fragment required_swap %}hi{% end %}")
        contract = PageShellContract(
            name="shell",
            targets=(
                PageShellTarget(target_id="main", fragment_block="required_swap", required=True),
            ),
        )
        app._mutable_state.fragment_target_registry.register_contract(contract)
        result = check_hypermedia_surface(app)
        shell_issues = [
            i for i in result.issues if i.category in {"page_shell", "fragment_target_orphan"}
        ]
        assert shell_issues == []
