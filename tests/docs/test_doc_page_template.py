"""Snapshot-style tests for ``chirp_docs/doc_page.html``.

Sprint 3.2 reworked the template to iterate ``doc.blocks`` instead of
dumping a monolithic ``doc.html``.  The joined block HTML equals
``doc.html`` byte-for-byte (``_split_blocks`` slices the original
string, so concatenation is lossless), so the rendered ``<article>``
region is semantically identical whichever branch the template takes.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from kida import Environment, PackageLoader

from chirp.docs.frontmatter import parse_file


@pytest.fixture
def docs_content(tmp_path: Path) -> Path:
    d = tmp_path / "content"
    d.mkdir()
    (d / "intro.md").write_text(
        "---\ntitle: Intro\n---\n"
        "Lead-in prose goes here.\n\n"
        "## Overview\n\nOverview body.\n\n"
        "## Details\n\nDetails body with **emphasis**.\n",
        encoding="utf-8",
    )
    return d


@pytest.fixture
def env() -> Environment:
    from chirp.templating.suspense import DEFERRED

    e = Environment(
        loader=PackageLoader("chirp.docs", "templates"),
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    e.add_test("deferred", lambda v: v is DEFERRED)
    return e


def _render_doc_content_block(env: Environment, doc) -> str:
    template = env.get_template("chirp_docs/doc_page.html")
    return template.render_block(
        "doc_content",
        {"doc": doc, "docs_nav_items": (), "docs_prefix": "/docs"},
    )


class TestDocPageTemplate:
    def test_joined_blocks_equal_doc_html(self, docs_content: Path) -> None:
        doc = parse_file(docs_content / "intro.md", docs_content)
        joined = "".join(str(b.html) for b in doc.blocks)
        assert joined == str(doc.html)

    def test_doc_content_block_contains_all_sections(
        self, env: Environment, docs_content: Path
    ) -> None:
        doc = parse_file(docs_content / "intro.md", docs_content)
        rendered = _render_doc_content_block(env, doc)

        assert "Lead-in prose" in rendered
        assert "Overview body" in rendered
        assert "Details body" in rendered
        assert "<strong>emphasis</strong>" in rendered
        assert '<article id="doc_content"' in rendered
        assert "</article>" in rendered

    def test_inner_html_identical_blocks_path_vs_fallback(
        self, env: Environment, docs_content: Path
    ) -> None:
        """The blocks-loop branch and the doc.html fallback produce the
        same inner HTML (whitespace around the content may differ but
        the meaningful bytes match)."""
        from dataclasses import replace

        doc_with_blocks = parse_file(docs_content / "intro.md", docs_content)
        doc_without_blocks = replace(doc_with_blocks, blocks=())

        with_blocks = _render_doc_content_block(env, doc_with_blocks)
        without_blocks = _render_doc_content_block(env, doc_without_blocks)

        inner_with = _article_inner(with_blocks).strip()
        inner_without = _article_inner(without_blocks).strip()
        assert inner_with == inner_without

    def test_empty_blocks_falls_back_to_doc_html(
        self, env: Environment, docs_content: Path
    ) -> None:
        """Autodoc pages (blocks=()) still render via doc.html."""
        from dataclasses import replace

        doc = parse_file(docs_content / "intro.md", docs_content)
        doc_no_blocks = replace(doc, blocks=())
        rendered = _render_doc_content_block(env, doc_no_blocks)

        assert "Lead-in prose" in rendered
        assert "Overview" in rendered

    def test_deferred_doc_renders_skeleton(self, env: Environment) -> None:
        from chirp.templating.suspense import DEFERRED

        template = env.get_template("chirp_docs/doc_page.html")
        rendered = template.render_block(
            "doc_content",
            {"doc": DEFERRED, "docs_nav_items": (), "docs_prefix": "/docs"},
        )
        assert "chirp-docs-skeleton" in rendered
        assert "Loading content" in rendered


_ARTICLE_INNER_RE = re.compile(
    r'<article id="doc_content"[^>]*>(.*)</article>',
    re.DOTALL,
)


def _article_inner(html: str) -> str:
    m = _ARTICLE_INNER_RE.search(html)
    assert m is not None, f"No <article id='doc_content'> found in:\n{html}"
    return m.group(1)
