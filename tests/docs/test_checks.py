"""Tests for chirp.docs.checks — contract checks for documentation integrity."""

from __future__ import annotations

from pathlib import Path

from chirp import App, AppConfig
from chirp.contracts import check_hypermedia_surface
from chirp.testing import TestClient


def _write_md(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_app(tmp_path: Path, *, content_files: dict[str, str], **plugin_kwargs):
    """Helper: create an app with DocsPlugin and given markdown files."""
    from chirp.docs import DocsPlugin

    content = tmp_path / "content"
    content.mkdir(exist_ok=True)
    for name, text in content_files.items():
        _write_md(content / name, text)

    tpl_dir = tmp_path / "templates"
    tpl_dir.mkdir(exist_ok=True)
    app = App(AppConfig(template_dir=str(tpl_dir)))
    app.mount("/docs", DocsPlugin(content_dir=content, **plugin_kwargs))
    return app


# ── check_docs_parseable ────────────────────────────────────────────────


class TestDocsParseable:
    def test_valid_files_no_issues(self, tmp_path: Path) -> None:
        app = _make_app(
            tmp_path,
            content_files={
                "guide.md": "---\ntitle: Guide\n---\n# Guide\n\nContent.",
                "ref.md": "---\ntitle: Reference\n---\n# Reference\n\nMore.",
            },
        )
        app.freeze()
        result = check_hypermedia_surface(app)
        parse_issues = [i for i in result.issues if i.category == "docs_parse"]
        assert len(parse_issues) == 0

    def test_broken_file_detected(self, tmp_path: Path) -> None:
        """The parse check re-parses files independently and catches errors.

        To trigger this, we add a broken file *after* the collection loads
        (which skips it), so the check sees it in the content_dir.
        """
        from chirp.docs import DocsPlugin

        content = tmp_path / "content"
        content.mkdir()
        _write_md(content / "good.md", "---\ntitle: Good\n---\n# Good")

        tpl_dir = tmp_path / "templates"
        tpl_dir.mkdir()
        app = App(AppConfig(template_dir=str(tpl_dir)))
        app.mount("/docs", DocsPlugin(content_dir=content))

        # Add broken file after mount (DocsCollection.load already ran)
        (content / "broken.md").write_bytes(b"\x80\x81\x82\x83")

        app.freeze()
        result = check_hypermedia_surface(app)

        parse_issues = [i for i in result.issues if i.category == "docs_parse"]
        assert len(parse_issues) >= 1
        assert "broken.md" in parse_issues[0].message


# ── check_docs_no_duplicate_slugs ───────────────────────────────────────


class TestNoDuplicateSlugs:
    def test_no_duplicates(self, tmp_path: Path) -> None:
        app = _make_app(
            tmp_path,
            content_files={
                "guide.md": "---\ntitle: Guide\n---\n# Guide",
                "ref.md": "---\ntitle: Reference\n---\n# Reference",
            },
        )
        app.freeze()
        result = check_hypermedia_surface(app)
        dup_issues = [i for i in result.issues if i.category == "docs_duplicate_slug"]
        assert len(dup_issues) == 0

    async def test_autodoc_no_collision_with_markdown(self, tmp_path: Path) -> None:
        """Autodoc pages use api/ prefix so no collision with user docs."""
        app = _make_app(
            tmp_path,
            content_files={
                "guide.md": "---\ntitle: Guide\n---\n# Guide",
            },
            autodoc=True,
        )

        @app.route("/api/health")
        def health():
            """Health check."""
            return "ok"

        async with TestClient(app) as _client:
            result = check_hypermedia_surface(app)
            dup_issues = [i for i in result.issues if i.category == "docs_duplicate_slug"]
            assert len(dup_issues) == 0


# ── check_docs_cross_references ─────────────────────────────────────────


class TestCrossReferences:
    def test_valid_references_no_issues(self, tmp_path: Path) -> None:
        app = _make_app(
            tmp_path,
            content_files={
                "guide.md": (
                    "---\ntitle: Guide\n---\n# Guide\n\nSee the [Reference](ref) for details."
                ),
                "ref.md": "---\ntitle: Reference\n---\n# Reference",
            },
        )
        app.freeze()
        result = check_hypermedia_surface(app)
        ref_issues = [i for i in result.issues if i.category == "docs_cross_ref"]
        assert len(ref_issues) == 0

    def test_broken_reference_detected(self, tmp_path: Path) -> None:
        app = _make_app(
            tmp_path,
            content_files={
                "guide.md": (
                    "---\ntitle: Guide\n---\n# Guide\n\n"
                    "See the [Missing Page](nonexistent) for details."
                ),
            },
        )
        app.freeze()
        result = check_hypermedia_surface(app)
        ref_issues = [i for i in result.issues if i.category == "docs_cross_ref"]
        assert len(ref_issues) == 1
        assert "nonexistent" in ref_issues[0].message
        assert "guide" in ref_issues[0].message

    def test_external_links_ignored(self, tmp_path: Path) -> None:
        app = _make_app(
            tmp_path,
            content_files={
                "guide.md": (
                    "---\ntitle: Guide\n---\n# Guide\n\n"
                    "See [Google](https://google.com) and [anchor](#section)."
                ),
            },
        )
        app.freeze()
        result = check_hypermedia_surface(app)
        ref_issues = [i for i in result.issues if i.category == "docs_cross_ref"]
        assert len(ref_issues) == 0

    def test_prefixed_reference_resolved(self, tmp_path: Path) -> None:
        app = _make_app(
            tmp_path,
            content_files={
                "guide.md": ("---\ntitle: Guide\n---\n# Guide\n\nSee the [Reference](/docs/ref)."),
                "ref.md": "---\ntitle: Reference\n---\n# Reference",
            },
        )
        app.freeze()
        result = check_hypermedia_surface(app)
        ref_issues = [i for i in result.issues if i.category == "docs_cross_ref"]
        assert len(ref_issues) == 0

    def test_file_links_with_extension_ignored(self, tmp_path: Path) -> None:
        app = _make_app(
            tmp_path,
            content_files={
                "guide.md": (
                    "---\ntitle: Guide\n---\n# Guide\n\nDownload the [file](example.pdf)."
                ),
            },
        )
        app.freeze()
        result = check_hypermedia_surface(app)
        ref_issues = [i for i in result.issues if i.category == "docs_cross_ref"]
        assert len(ref_issues) == 0


# ── check_docs_no_drafts_exposed ────────────────────────────────────────


class TestNoDraftsExposed:
    def test_no_drafts_in_collection(self, tmp_path: Path) -> None:
        app = _make_app(
            tmp_path,
            content_files={
                "guide.md": "---\ntitle: Guide\n---\n# Guide",
            },
        )
        app.freeze()
        result = check_hypermedia_surface(app)
        draft_issues = [i for i in result.issues if i.category == "docs_draft_exposed"]
        assert len(draft_issues) == 0

    def test_drafts_included_no_warning(self, tmp_path: Path) -> None:
        """When include_drafts=True, draft pages are expected — no warning."""
        app = _make_app(
            tmp_path,
            content_files={
                "draft.md": "---\ntitle: Draft\ndraft: true\n---\n# Draft",
            },
            include_drafts=True,
        )
        app.freeze()
        result = check_hypermedia_surface(app)
        draft_issues = [i for i in result.issues if i.category == "docs_draft_exposed"]
        assert len(draft_issues) == 0


# ── Integration: app.check() with docs ──────────────────────────────────


class TestAppCheckIntegration:
    def test_app_check_passes_clean_docs(self, tmp_path: Path) -> None:
        app = _make_app(
            tmp_path,
            content_files={
                "guide.md": "---\ntitle: Guide\n---\n# Guide\n\nContent.",
            },
        )
        # Should not raise
        app.freeze()
        app.check()

    async def test_app_check_with_autodoc(self, tmp_path: Path) -> None:
        app = _make_app(
            tmp_path,
            content_files={
                "guide.md": "---\ntitle: Guide\n---\n# Guide\n\nContent.",
            },
            autodoc=True,
        )

        @app.route("/api/health")
        def health():
            """Health check."""
            return "ok"

        async with TestClient(app) as _client:
            # check() should pass — autodoc pages have unique slugs
            app.check()
