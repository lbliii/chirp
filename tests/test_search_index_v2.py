"""Sprint 4.1 — SearchEntry v2 manifest + block-level entries."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from chirp import App, AppConfig
from chirp.docs import DocsPlugin
from chirp.freeze import BlockEntry, SearchEntry, freeze


@pytest.fixture
def docs_app(tmp_path: Path) -> App:
    content = tmp_path / "content"
    content.mkdir()
    (content / "intro.md").write_text(
        "---\ntitle: Intro\ncategory: Start\n---\n"
        "Lead prose.\n\n"
        "## Overview\n\nBody of overview with **bold**.\n\n"
        "## Details\n\nBody of details.\n",
        encoding="utf-8",
    )
    tpl = tmp_path / "tpl"
    tpl.mkdir()
    app = App(AppConfig(template_dir=str(tpl), debug=False))
    app.mount("/docs", DocsPlugin(content_dir=content, title="Test", autodoc=False))
    return app


def _load_manifest(output: Path) -> dict:
    raw = (output / "_search-index.js").read_text()
    return json.loads(raw.removeprefix("window.__chirp_search=").removesuffix(";"))


class TestSearchEntryV2:
    async def test_manifest_is_version_2(self, docs_app: App, tmp_path: Path) -> None:
        output = tmp_path / "dist"
        await freeze(docs_app, output)
        data = _load_manifest(output)
        assert data["version"] == 2

    async def test_doc_entry_has_blocks(self, docs_app: App, tmp_path: Path) -> None:
        output = tmp_path / "dist"
        await freeze(docs_app, output)
        data = _load_manifest(output)
        intro = next(e for e in data["entries"] if e["t"] == "Intro")
        assert "blocks" in intro
        block_ids = {b["id"] for b in intro["blocks"]}
        assert "overview" in block_ids
        assert "details" in block_ids

    async def test_block_body_is_plain_text(self, docs_app: App, tmp_path: Path) -> None:
        """Block body must have tags stripped for match scoring."""
        output = tmp_path / "dist"
        await freeze(docs_app, output)
        data = _load_manifest(output)
        intro = next(e for e in data["entries"] if e["t"] == "Intro")
        overview = next(b for b in intro["blocks"] if b["id"] == "overview")
        assert "<" not in overview["b"]
        assert ">" not in overview["b"]
        assert "bold" in overview["b"]

    async def test_block_fields_present(self, docs_app: App, tmp_path: Path) -> None:
        output = tmp_path / "dist"
        await freeze(docs_app, output)
        data = _load_manifest(output)
        intro = next(e for e in data["entries"] if e["t"] == "Intro")
        overview = next(b for b in intro["blocks"] if b["id"] == "overview")
        assert overview["h"] == "Overview"
        assert overview["a"] == "overview"
        assert overview["d"] == 2

    async def test_blocks_absent_when_no_block_data(self, docs_app: App, tmp_path: Path) -> None:
        """Entries from non-docs contributions (no blocks) omit the key entirely.

        v1 readers that ignore unknown fields see the same shape they always did.
        """
        tpl = tmp_path / "tpl"
        tpl.mkdir(exist_ok=True)
        app = App(AppConfig(template_dir=str(tpl), debug=False))

        @app.route("/")
        def index():
            from chirp.freeze import search_contribute

            search_contribute(SearchEntry(url="/", title="Home", body="Plain page"))
            return "<html><body><h1>Home</h1></body></html>"

        output = tmp_path / "dist2"
        await freeze(app, output)
        data = _load_manifest(output)
        home = next(e for e in data["entries"] if e["t"] == "Home")
        assert "blocks" not in home


class TestBlockEntryDataclass:
    def test_frozen_immutable(self) -> None:
        from dataclasses import FrozenInstanceError

        entry = BlockEntry(block_id="x", heading="X", body="y", anchor="x", depth=2)
        with pytest.raises(FrozenInstanceError):
            entry.heading = "Z"  # type: ignore[misc]

    def test_default_blocks_on_search_entry(self) -> None:
        entry = SearchEntry(url="/", title="T")
        assert entry.blocks == ()
