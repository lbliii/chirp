"""Tests for chirp.docs.collection — DocsCollection load, query, merge."""

from __future__ import annotations

from pathlib import Path

from kida.template import Markup

from chirp.docs.models import DocMetadata, DocPage, DocSource


def _make_page(
    slug: str,
    title: str = "",
    *,
    order: int = 999,
    category: str = "",
    draft: bool = False,
    raw: str = "",
) -> DocPage:
    return DocPage(
        slug=slug,
        title=title or slug.replace("-", " ").title(),
        raw=raw or f"# {title or slug}\n\nBody.",
        html=Markup(f"<h1>{title or slug}</h1><p>Body.</p>"),
        toc=(),
        metadata=DocMetadata(
            order=order,
            category=category,
            draft=draft,
        ),
        source=DocSource.MARKDOWN,
    )


# ── Constructor & basic queries ──────────────────────────────────────────


class TestDocsCollection:
    def test_get_by_slug(self) -> None:
        from chirp.docs.collection import DocsCollection

        p = _make_page("intro")
        coll = DocsCollection((p,))
        assert coll.get("intro") is p

    def test_get_missing(self) -> None:
        from chirp.docs.collection import DocsCollection

        coll = DocsCollection(())
        assert coll.get("nope") is None

    def test_contains(self) -> None:
        from chirp.docs.collection import DocsCollection

        coll = DocsCollection((_make_page("a"),))
        assert "a" in coll
        assert "b" not in coll

    def test_len(self) -> None:
        from chirp.docs.collection import DocsCollection

        coll = DocsCollection((_make_page("a"), _make_page("b")))
        assert len(coll) == 2

    def test_list_sorted_by_order(self) -> None:
        from chirp.docs.collection import DocsCollection

        pages = (
            _make_page("c", order=3),
            _make_page("a", order=1),
            _make_page("b", order=2),
        )
        coll = DocsCollection(pages)
        slugs = [p.slug for p in coll.list()]
        assert slugs == ["a", "b", "c"]

    def test_list_by_category(self) -> None:
        from chirp.docs.collection import DocsCollection

        pages = (
            _make_page("a", category="Guide"),
            _make_page("b", category="API"),
            _make_page("c", category="Guide"),
        )
        coll = DocsCollection(pages)
        guides = coll.list(category="Guide")
        assert len(guides) == 2
        assert all(p.metadata.category == "Guide" for p in guides)

    def test_categories(self) -> None:
        from chirp.docs.collection import DocsCollection

        pages = (
            _make_page("a", category="Guide"),
            _make_page("b", category="API"),
            _make_page("c", category="Guide"),
        )
        coll = DocsCollection(pages)
        assert coll.categories() == ("API", "Guide")

    def test_as_nav(self) -> None:
        from chirp.docs.collection import DocsCollection

        pages = (
            _make_page("b", order=2, category="Guide"),
            _make_page("a", order=1, category="Guide"),
            _make_page("c", order=1, category="API"),
        )
        coll = DocsCollection(pages)
        nav = coll.as_nav()
        assert len(nav) == 2
        assert nav[0].category == "API"
        assert nav[1].category == "Guide"
        # Within Guide, sorted by order
        assert nav[1].pages[0].slug == "a"
        assert nav[1].pages[1].slug == "b"


# ── Merge ────────────────────────────────────────────────────────────────


class TestMerge:
    def test_merge_combines(self) -> None:
        from chirp.docs.collection import DocsCollection

        c1 = DocsCollection((_make_page("a"),))
        c2 = DocsCollection((_make_page("b"),))
        merged = c1.merge(c2)
        assert len(merged) == 2
        assert "a" in merged
        assert "b" in merged

    def test_merge_overwrites(self) -> None:
        from chirp.docs.collection import DocsCollection

        p1 = _make_page("x", "Old Title")
        p2 = _make_page("x", "New Title")
        c1 = DocsCollection((p1,))
        c2 = DocsCollection((p2,))
        merged = c1.merge(c2)
        assert merged.get("x").title == "New Title"


# ── Load from disk ───────────────────────────────────────────────────────


class TestLoad:
    def _write_md(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def test_loads_directory(self, tmp_path: Path) -> None:
        from chirp.docs.collection import DocsCollection

        self._write_md(
            tmp_path / "intro.md",
            "---\ntitle: Intro\norder: 1\ncategory: Guide\n---\n# Intro\n",
        )
        self._write_md(
            tmp_path / "setup.md",
            "---\ntitle: Setup\norder: 2\ncategory: Guide\n---\n# Setup\n",
        )
        self._write_md(
            tmp_path / "api/routes.md",
            "---\ntitle: Routes\norder: 1\ncategory: API\n---\n# Routes\n",
        )

        coll = DocsCollection.load(tmp_path)
        assert len(coll) == 3
        assert coll.get("intro") is not None
        assert coll.get("api/routes") is not None
        assert coll.categories() == ("API", "Guide")

    def test_excludes_drafts(self, tmp_path: Path) -> None:
        from chirp.docs.collection import DocsCollection

        self._write_md(
            tmp_path / "published.md",
            "---\ntitle: Published\n---\nContent",
        )
        self._write_md(
            tmp_path / "wip.md",
            "---\ntitle: WIP\ndraft: true\n---\nContent",
        )
        coll = DocsCollection.load(tmp_path)
        assert len(coll) == 1
        assert coll.get("published") is not None

    def test_includes_drafts_when_requested(self, tmp_path: Path) -> None:
        from chirp.docs.collection import DocsCollection

        self._write_md(
            tmp_path / "wip.md",
            "---\ntitle: WIP\ndraft: true\n---\nContent",
        )
        coll = DocsCollection.load(tmp_path, include_drafts=True)
        assert len(coll) == 1

    def test_sorted_by_order_then_title(self, tmp_path: Path) -> None:
        from chirp.docs.collection import DocsCollection

        self._write_md(tmp_path / "z.md", "---\ntitle: Z\norder: 1\n---\n# Z")
        self._write_md(tmp_path / "a.md", "---\ntitle: A\norder: 2\n---\n# A")
        self._write_md(tmp_path / "m.md", "---\ntitle: M\norder: 1\n---\n# M")

        coll = DocsCollection.load(tmp_path)
        listed = coll.list()
        assert [p.title for p in listed] == ["M", "Z", "A"]

    def test_empty_directory(self, tmp_path: Path) -> None:
        from chirp.docs.collection import DocsCollection

        coll = DocsCollection.load(tmp_path)
        assert len(coll) == 0
