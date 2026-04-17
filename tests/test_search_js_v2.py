"""Sprint 4.3 — Client-side search consumes block entries.

Structural assertions on `_STATIC_SEARCH_JS` plus an integration test
that confirms the injected script in a frozen doc page contains the
block-aware logic.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from chirp import App, AppConfig
from chirp.docs import DocsPlugin
from chirp.freeze import _STATIC_SEARCH_JS, freeze


class TestStaticSearchJsStructure:
    def test_references_block_array(self) -> None:
        """JS reads `p.blocks` from v2 manifest entries."""
        assert "p.blocks" in _STATIC_SEARCH_JS

    def test_scores_block_heading_and_body(self) -> None:
        """Block heading and body are scored via `b.h` / `b.b` accessors."""
        assert "b.h" in _STATIC_SEARCH_JS
        assert "b.b" in _STATIC_SEARCH_JS

    def test_constructs_deep_link_anchor(self) -> None:
        """When a block wins, href includes `#` + `block.a`."""
        assert "'#'+r.block.a" in _STATIC_SEARCH_JS

    def test_renders_block_heading_in_result(self) -> None:
        """Block results render page title, separator, and block heading."""
        assert "r.block.h" in _STATIC_SEARCH_JS
        assert "\\u203a" in _STATIC_SEARCH_JS  # U+203A separator

    def test_falls_back_to_page_when_no_block_match(self) -> None:
        """`ps>0` branch means page-level match still works without blocks."""
        assert "else if(ps>0)" in _STATIC_SEARCH_JS

    def test_block_score_tiebreak_prefers_block(self) -> None:
        """Block wins on `>=` so a tied score deep-links to the section."""
        assert "bestScore>=ps" in _STATIC_SEARCH_JS


@pytest.fixture
def docs_app(tmp_path: Path) -> App:
    content = tmp_path / "content"
    content.mkdir()
    (content / "intro.md").write_text(
        "---\ntitle: Intro\n---\n"
        "Lead prose.\n\n"
        "## Overview\n\nOverview body.\n\n"
        "## Details\n\nDetails body.\n",
        encoding="utf-8",
    )
    tpl = tmp_path / "tpl"
    tpl.mkdir()
    app = App(AppConfig(template_dir=str(tpl), debug=False))
    app.mount("/docs", DocsPlugin(content_dir=content, title="Test", autodoc=False))
    return app


class TestStaticSearchJsInjection:
    async def test_injected_script_has_block_logic(self, docs_app: App, tmp_path: Path) -> None:
        output = tmp_path / "dist"
        await freeze(docs_app, output)
        index_html = (output / "docs" / "index.html").read_text()
        assert 'data-chirp="static-search"' in index_html
        assert "p.blocks" in index_html
        assert "'#'+r.block.a" in index_html

    async def test_depth_placeholder_replaced(self, docs_app: App, tmp_path: Path) -> None:
        """`__DEPTH__` is substituted with the page's directory depth."""
        output = tmp_path / "dist"
        await freeze(docs_app, output)
        index_html = (output / "docs" / "index.html").read_text()
        assert "__DEPTH__" not in index_html
