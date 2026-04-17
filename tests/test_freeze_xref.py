"""Sprint 4.2 — Cross-link graph (`_xref.json`) emission during freeze."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from chirp import App, AppConfig
from chirp.freeze import _build_xref_graph, _extract_internal_hrefs, freeze


class TestExtractInternalHrefs:
    def test_collects_internal_hrefs(self) -> None:
        html = '<a href="/docs/a">A</a><a href="/docs/b">B</a>'
        known = frozenset({"/docs/a", "/docs/b"})
        assert _extract_internal_hrefs(html, known) == ["/docs/a", "/docs/b"]

    def test_strips_fragment_and_query(self) -> None:
        html = '<a href="/docs/a#section">A</a><a href="/docs/b?x=1">B</a>'
        known = frozenset({"/docs/a", "/docs/b"})
        assert sorted(_extract_internal_hrefs(html, known)) == ["/docs/a", "/docs/b"]

    def test_filters_unknown_urls(self) -> None:
        html = '<a href="/docs/a">A</a><a href="/no-such">X</a>'
        known = frozenset({"/docs/a"})
        assert _extract_internal_hrefs(html, known) == ["/docs/a"]

    def test_ignores_external(self) -> None:
        html = '<a href="https://example.com">Ext</a><a href="mailto:x@y">M</a>'
        assert _extract_internal_hrefs(html, frozenset()) == []

    def test_deduplicates(self) -> None:
        html = '<a href="/docs/a">1</a><a href="/docs/a">2</a>'
        known = frozenset({"/docs/a"})
        assert _extract_internal_hrefs(html, known) == ["/docs/a"]


class TestBuildXrefGraph:
    def test_three_page_fixture(self) -> None:
        known = frozenset({"/a", "/b", "/c"})
        rendered = [
            ("/a", '<a href="/b">to b</a><a href="/c">to c</a>'),
            ("/b", '<a href="/c">to c</a>'),
            ("/c", "<p>leaf</p>"),
        ]
        graph = _build_xref_graph(rendered, known)
        assert graph["version"] == 1
        assert graph["pages"]["/a"]["references"] == ["/b", "/c"]
        assert graph["pages"]["/a"]["referenced_by"] == []
        assert graph["pages"]["/b"]["references"] == ["/c"]
        assert graph["pages"]["/b"]["referenced_by"] == ["/a"]
        assert graph["pages"]["/c"]["references"] == []
        assert graph["pages"]["/c"]["referenced_by"] == ["/a", "/b"]

    def test_deterministic_output(self) -> None:
        """Same input → identical JSON bytes."""
        known = frozenset({"/a", "/b", "/c"})
        rendered = [
            ("/a", '<a href="/c">c</a><a href="/b">b</a>'),
            ("/b", '<a href="/a">a</a>'),
            ("/c", "<p>leaf</p>"),
        ]
        first = json.dumps(_build_xref_graph(rendered, known), sort_keys=False)
        second = json.dumps(_build_xref_graph(rendered, known), sort_keys=False)
        assert first == second

    def test_excludes_self_references(self) -> None:
        known = frozenset({"/a"})
        rendered = [("/a", '<a href="/a">self</a>')]
        graph = _build_xref_graph(rendered, known)
        assert graph["pages"]["/a"]["references"] == []

    def test_empty_input_produces_empty_pages(self) -> None:
        graph = _build_xref_graph([], frozenset())
        assert graph == {"version": 1, "pages": {}}


@pytest.fixture
def linked_app(tmp_path: Path) -> App:
    tpl = tmp_path / "tpl"
    tpl.mkdir()
    app = App(AppConfig(template_dir=str(tpl), debug=False))

    @app.route("/")
    def home():
        return '<html><body><a href="/a">A</a><a href="/b">B</a></body></html>'

    @app.route("/a")
    def a():
        return '<html><body><a href="/b">B</a></body></html>'

    @app.route("/b")
    def b():
        return "<html><body>Leaf</body></html>"

    return app


class TestXrefFreezeIntegration:
    async def test_xref_file_written(self, linked_app: App, tmp_path: Path) -> None:
        output = tmp_path / "dist"
        await freeze(linked_app, output)
        assert (output / "_xref.json").exists()

    async def test_xref_contents(self, linked_app: App, tmp_path: Path) -> None:
        output = tmp_path / "dist"
        await freeze(linked_app, output)
        data = json.loads((output / "_xref.json").read_text())
        assert data["version"] == 1
        assert data["pages"]["/"]["references"] == ["/a", "/b"]
        assert data["pages"]["/a"]["references"] == ["/b"]
        assert data["pages"]["/b"]["referenced_by"] == ["/", "/a"]

    async def test_xref_size_under_10kb(self, linked_app: App, tmp_path: Path) -> None:
        """Acceptance: <10KB for small sites."""
        output = tmp_path / "dist"
        await freeze(linked_app, output)
        size = (output / "_xref.json").stat().st_size
        assert size < 10 * 1024, f"xref file is {size} bytes, expected <10KB"
