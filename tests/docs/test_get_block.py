"""Tests for ``DocsCollection.get_block()`` — Sprint 3.3."""

from __future__ import annotations

import pytest
from kida.template import Markup

from chirp.docs import DocsCollection
from chirp.docs.models import DocBlock, DocMetadata, DocPage, DocSource


def _make_page(slug: str, blocks: tuple[DocBlock, ...]) -> DocPage:
    html = Markup("".join(str(b.html) for b in blocks))
    return DocPage(
        slug=slug,
        title=slug.replace("-", " ").title(),
        raw="",
        html=html,
        toc=(),
        metadata=DocMetadata(),
        source=DocSource.MARKDOWN,
        source_path=None,
        blocks=blocks,
    )


@pytest.fixture
def collection() -> DocsCollection:
    intro_blocks = (
        DocBlock(
            id="intro",
            heading="",
            html=Markup("<p>Welcome.</p>"),
            depth=0,
            anchor="",
        ),
        DocBlock(
            id="overview",
            heading="Overview",
            html=Markup('<h2 id="overview">Overview</h2><p>Overview body.</p>'),
            depth=2,
            anchor="overview",
        ),
        DocBlock(
            id="details",
            heading="Details",
            html=Markup('<h2 id="details">Details</h2><p>Details body.</p>'),
            depth=2,
            anchor="details",
        ),
    )
    nested_blocks = (
        DocBlock(
            id="subsection_a",
            heading="Subsection A",
            html=Markup('<h3 id="subsection-a">A</h3><p>sub a body</p>'),
            depth=3,
            anchor="subsection-a",
        ),
    )
    return DocsCollection(
        (
            _make_page("intro", intro_blocks),
            _make_page("nested", nested_blocks),
            _make_page("empty", ()),
        )
    )


class TestGetBlock:
    def test_returns_existing_block(self, collection: DocsCollection) -> None:
        block = collection.get_block("intro", "overview")
        assert block is not None
        assert block.id == "overview"
        assert block.heading == "Overview"
        assert block.depth == 2
        assert "Overview body" in block.html

    def test_unknown_block_returns_none(self, collection: DocsCollection) -> None:
        assert collection.get_block("intro", "nonexistent") is None

    def test_unknown_slug_returns_none(self, collection: DocsCollection) -> None:
        assert collection.get_block("no-such-page", "overview") is None

    def test_nested_depth_block(self, collection: DocsCollection) -> None:
        block = collection.get_block("nested", "subsection_a")
        assert block is not None
        assert block.depth == 3
        assert block.anchor == "subsection-a"

    def test_page_with_no_blocks(self, collection: DocsCollection) -> None:
        assert collection.get_block("empty", "anything") is None

    def test_intro_block_retrievable(self, collection: DocsCollection) -> None:
        block = collection.get_block("intro", "intro")
        assert block is not None
        assert block.depth == 0
        assert block.heading == ""
