"""Tests for chirp.docs.frontmatter — YAML parsing, title extraction, TOC."""

from __future__ import annotations

from pathlib import Path

# ── parse_frontmatter ────────────────────────────────────────────────────


class TestParseFrontmatter:
    def test_valid_yaml(self) -> None:
        from chirp.docs.frontmatter import parse_frontmatter

        text = "---\ntitle: Hello\norder: 1\n---\n# Body"
        meta, body = parse_frontmatter(text)
        assert meta["title"] == "Hello"
        assert meta["order"] == 1
        assert body == "# Body"

    def test_no_frontmatter(self) -> None:
        from chirp.docs.frontmatter import parse_frontmatter

        text = "# Just a heading\n\nSome content."
        meta, body = parse_frontmatter(text)
        assert meta == {}
        assert body == text

    def test_empty_string(self) -> None:
        from chirp.docs.frontmatter import parse_frontmatter

        meta, body = parse_frontmatter("")
        assert meta == {}
        assert body == ""

    def test_draft_flag(self) -> None:
        from chirp.docs.frontmatter import parse_frontmatter

        text = "---\ntitle: WIP\ndraft: true\n---\nContent"
        meta, _ = parse_frontmatter(text)
        assert meta["draft"] is True

    def test_tags_as_list(self) -> None:
        from chirp.docs.frontmatter import parse_frontmatter

        text = "---\ntags:\n  - python\n  - web\n---\nBody"
        meta, _ = parse_frontmatter(text)
        assert meta["tags"] == ["python", "web"]

    def test_unicode_content(self) -> None:
        from chirp.docs.frontmatter import parse_frontmatter

        text = "---\ntitle: Über Guide\ndescription: Ñoño\n---\nCafé"
        meta, body = parse_frontmatter(text)
        assert meta["title"] == "Über Guide"
        assert body == "Café"


# ── _meta_from_dict ──────────────────────────────────────────────────────


class TestMetaFromDict:
    def test_full_metadata(self) -> None:
        from chirp.docs.frontmatter import _meta_from_dict

        meta = _meta_from_dict(
            {
                "order": 2,
                "category": "Guides",
                "tags": ["a", "b"],
                "description": "A guide",
                "draft": False,
            }
        )
        assert meta.order == 2
        assert meta.category == "Guides"
        assert meta.tags == frozenset({"a", "b"})
        assert meta.description == "A guide"
        assert meta.draft is False

    def test_defaults(self) -> None:
        from chirp.docs.frontmatter import _meta_from_dict

        meta = _meta_from_dict({})
        assert meta.order == 999
        assert meta.category == ""
        assert meta.tags == frozenset()
        assert meta.description == ""
        assert meta.draft is False

    def test_tags_as_csv_string(self) -> None:
        from chirp.docs.frontmatter import _meta_from_dict

        meta = _meta_from_dict({"tags": "python, web, chirp"})
        assert meta.tags == frozenset({"python", "web", "chirp"})


# ── Title extraction ─────────────────────────────────────────────────────


class TestTitleExtraction:
    def test_from_heading(self) -> None:
        from chirp.docs.frontmatter import _title_from_body

        assert _title_from_body("# Getting Started") == "Getting Started"

    def test_h2_fallback(self) -> None:
        from chirp.docs.frontmatter import _title_from_body

        assert _title_from_body("## Sub Heading") == "Sub Heading"

    def test_no_heading(self) -> None:
        from chirp.docs.frontmatter import _title_from_body

        assert _title_from_body("Just a paragraph.") == ""


# ── TOC extraction ───────────────────────────────────────────────────────


class TestTocExtraction:
    def test_extracts_headings(self) -> None:
        from chirp.docs.frontmatter import _extract_toc

        html = '<h1 id="intro">Introduction</h1><h2 id="setup">Setup</h2>'
        toc = _extract_toc(html)
        assert len(toc) == 2
        assert toc[0].level == 1
        assert toc[0].id == "intro"
        assert toc[0].text == "Introduction"
        assert toc[1].level == 2
        assert toc[1].id == "setup"

    def test_strips_inner_tags(self) -> None:
        from chirp.docs.frontmatter import _extract_toc

        html = '<h2 id="x"><code>code</code> heading</h2>'
        toc = _extract_toc(html)
        assert toc[0].text == "code heading"

    def test_no_headings(self) -> None:
        from chirp.docs.frontmatter import _extract_toc

        assert _extract_toc("<p>No headings here</p>") == ()


# ── Block splitting ─────────────────────────────────────────────────────


class TestSlugToIdentifier:
    def test_kebab_to_snake(self) -> None:
        from chirp.docs.frontmatter import _slug_to_identifier

        assert _slug_to_identifier("section-overview") == "section_overview"

    def test_strips_punctuation(self) -> None:
        from chirp.docs.frontmatter import _slug_to_identifier

        assert _slug_to_identifier("why?-how!") == "why_how"

    def test_leading_digit_prefixed(self) -> None:
        from chirp.docs.frontmatter import _slug_to_identifier

        assert _slug_to_identifier("1-intro") == "s_1_intro"

    def test_empty_fallback(self) -> None:
        from chirp.docs.frontmatter import _slug_to_identifier

        assert _slug_to_identifier("") == "section"
        assert _slug_to_identifier("---") == "section"

    def test_lowercases(self) -> None:
        from chirp.docs.frontmatter import _slug_to_identifier

        assert _slug_to_identifier("Section-One") == "section_one"


class TestSplitBlocks:
    def test_splits_on_h2(self) -> None:
        from chirp.docs.frontmatter import _split_blocks

        html = (
            "<p>Lead in.</p>"
            '<h2 id="alpha">Alpha</h2><p>A body.</p>'
            '<h2 id="beta">Beta</h2><p>B body.</p>'
        )
        blocks = _split_blocks(html)
        ids = [b.id for b in blocks]
        assert ids == ["intro", "alpha", "beta"]
        assert blocks[0].depth == 0
        assert blocks[1].depth == 2
        assert blocks[1].heading == "Alpha"
        assert blocks[1].anchor == "alpha"
        assert "A body." in blocks[1].html
        assert "B body." not in blocks[1].html
        assert "B body." in blocks[2].html

    def test_falls_back_to_h3(self) -> None:
        from chirp.docs.frontmatter import _split_blocks

        html = '<h3 id="one">One</h3><p>x</p><h3 id="two">Two</h3><p>y</p>'
        blocks = _split_blocks(html)
        assert [b.id for b in blocks] == ["one", "two"]
        assert all(b.depth == 3 for b in blocks)

    def test_no_headings_single_intro(self) -> None:
        from chirp.docs.frontmatter import _split_blocks

        blocks = _split_blocks("<p>Just prose.</p>")
        assert len(blocks) == 1
        assert blocks[0].id == "intro"
        assert blocks[0].depth == 0

    def test_empty_html_returns_empty(self) -> None:
        from chirp.docs.frontmatter import _split_blocks

        assert _split_blocks("") == ()
        assert _split_blocks("   \n  ") == ()

    def test_no_intro_when_heading_is_first(self) -> None:
        from chirp.docs.frontmatter import _split_blocks

        html = '<h2 id="alpha">Alpha</h2><p>A.</p>'
        blocks = _split_blocks(html)
        assert [b.id for b in blocks] == ["alpha"]

    def test_duplicate_ids_disambiguated(self) -> None:
        from chirp.docs.frontmatter import _split_blocks

        html = (
            '<h2 id="dup">One</h2><p>a</p>'
            '<h2 id="dup">Two</h2><p>b</p>'
            '<h2 id="dup">Three</h2><p>c</p>'
        )
        blocks = _split_blocks(html)
        assert [b.id for b in blocks] == ["dup", "dup_2", "dup_3"]
        assert [b.anchor for b in blocks] == ["dup", "dup", "dup"]

    def test_anchor_preserved_kebab(self) -> None:
        from chirp.docs.frontmatter import _split_blocks

        html = '<h2 id="section-overview">Overview</h2><p>x</p>'
        blocks = _split_blocks(html)
        assert blocks[0].id == "section_overview"
        assert blocks[0].anchor == "section-overview"

    def test_falls_back_to_heading_text_when_no_id(self) -> None:
        from chirp.docs.frontmatter import _split_blocks

        html = "<h2>Getting Started</h2><p>x</p>"
        blocks = _split_blocks(html)
        assert blocks[0].id == "getting_started"
        assert blocks[0].anchor == ""

    def test_h3_ignored_when_h2_present(self) -> None:
        from chirp.docs.frontmatter import _split_blocks

        html = '<h2 id="a">A</h2><p>x</p><h3 id="a1">A-sub</h3><p>y</p><h2 id="b">B</h2><p>z</p>'
        blocks = _split_blocks(html)
        assert [b.id for b in blocks] == ["a", "b"]
        assert "A-sub" in blocks[0].html
        assert "y" in blocks[0].html


# ── Slug derivation ─────────────────────────────────────────────────────


class TestSlugFromPath:
    def test_simple(self) -> None:
        from chirp.docs.frontmatter import _slug_from_path

        slug = _slug_from_path(Path("/docs/getting-started.md"), Path("/docs"))
        assert slug == "getting-started"

    def test_nested(self) -> None:
        from chirp.docs.frontmatter import _slug_from_path

        slug = _slug_from_path(Path("/docs/guides/routing.md"), Path("/docs"))
        assert slug == "guides/routing"

    def test_index_md(self) -> None:
        from chirp.docs.frontmatter import _slug_from_path

        slug = _slug_from_path(Path("/docs/guides/index.md"), Path("/docs"))
        assert slug == "guides"

    def test_underscore_index_md(self) -> None:
        from chirp.docs.frontmatter import _slug_from_path

        slug = _slug_from_path(Path("/docs/guides/_index.md"), Path("/docs"))
        assert slug == "guides"

    def test_readme_md(self) -> None:
        from chirp.docs.frontmatter import _slug_from_path

        slug = _slug_from_path(Path("/docs/guides/README.md"), Path("/docs"))
        assert slug == "guides"

    def test_root_index_md(self) -> None:
        from chirp.docs.frontmatter import _slug_from_path

        slug = _slug_from_path(Path("/docs/index.md"), Path("/docs"))
        assert slug == "index"

    def test_root_underscore_index_md(self) -> None:
        from chirp.docs.frontmatter import _slug_from_path

        slug = _slug_from_path(Path("/docs/_index.md"), Path("/docs"))
        assert slug == "index"

    def test_nested_deep_index(self) -> None:
        from chirp.docs.frontmatter import _slug_from_path

        slug = _slug_from_path(Path("/docs/api/v2/_index.md"), Path("/docs"))
        assert slug == "api/v2"


# ── parse_file (integration) ────────────────────────────────────────────


class TestParseFile:
    def test_full_parse(self, tmp_path: Path) -> None:
        from chirp.docs.frontmatter import parse_file
        from chirp.docs.models import DocSource

        md = tmp_path / "test.md"
        md.write_text(
            "---\ntitle: Test Page\norder: 1\ncategory: Guide\n---\n"
            "# Test Page\n\nSome content about **routing**.\n",
            encoding="utf-8",
        )
        page = parse_file(md, tmp_path)
        assert page.slug == "test"
        assert page.title == "Test Page"
        assert page.metadata.order == 1
        assert page.metadata.category == "Guide"
        assert page.source == DocSource.MARKDOWN
        assert page.source_path == md
        assert "<strong>" in page.html or "<b>" in page.html
        assert page.raw.startswith("# Test Page")

    def test_no_frontmatter_derives_title(self, tmp_path: Path) -> None:
        from chirp.docs.frontmatter import parse_file

        md = tmp_path / "guide.md"
        md.write_text("# My Guide\n\nBody text.", encoding="utf-8")
        page = parse_file(md, tmp_path)
        assert page.title == "My Guide"
        assert page.metadata.order == 999  # default

    def test_unicode_file(self, tmp_path: Path) -> None:
        from chirp.docs.frontmatter import parse_file

        md = tmp_path / "über.md"
        md.write_text(
            "---\ntitle: Über Guide\n---\n# Über\n\nCafé content.",
            encoding="utf-8",
        )
        page = parse_file(md, tmp_path)
        assert page.title == "Über Guide"
        assert "Café" in page.raw
