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
