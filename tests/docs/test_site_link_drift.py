"""Guards for stale public docs links."""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_SITE_DOCS = _ROOT / "site" / "content" / "docs"
_SITE_CONTENT = _ROOT / "site" / "content"

_INDEX_STEMS = frozenset({"index", "_index", "README"})
_CHIRP_DOC_LINK_RE = re.compile(r"(?:https://lbliii\.github\.io)?/chirp/docs/[^\s\])\"'<>]+")
_MARKDOWN_SAFE_PIPE_RE = re.compile(r"\|\s*markdown\s*\|\s*safe\b")


def _site_markdown_files() -> tuple[Path, ...]:
    return tuple(sorted(_SITE_DOCS.rglob("*.md")))


def _public_markdown_files() -> tuple[Path, ...]:
    return (Path("README.md"), *tuple(sorted(_SITE_CONTENT.rglob("*.md"))))


def _slug_from_path(path: Path) -> str:
    rel = path.relative_to(_SITE_DOCS)
    slug = str(rel.with_suffix("")).replace("\\", "/")
    if path.stem in _INDEX_STEMS:
        parent = str(rel.parent).replace("\\", "/")
        if parent == ".":
            return "index"
        return parent
    return slug


def _slug_from_doc_link(url: str) -> str:
    path = url.split("#", 1)[0].split("?", 1)[0].rstrip("/")
    slug = path.removeprefix("https://lbliii.github.io").removeprefix("/chirp/docs")
    return slug.strip("/") or "index"


def test_site_docs_do_not_link_to_unprefixed_docs_paths() -> None:
    """Published site links should include the /chirp base path."""
    offenders: list[str] = []
    for path in _site_markdown_files():
        text = path.read_text()
        if "](/docs/" in text:
            offenders.append(str(path.relative_to(_ROOT)))

    assert not offenders, (
        f"Use /chirp/docs/... for published site links instead of /docs/...: {offenders}"
    )


def test_site_docs_do_not_link_to_old_repository_owner() -> None:
    """The public docs should point at the canonical lbliii/chirp repo."""
    offenders: list[str] = []
    for path in _site_markdown_files():
        text = path.read_text()
        if "github.com/nvidia/chirp" in text:
            offenders.append(str(path.relative_to(_ROOT)))

    assert not offenders, (
        f"Replace github.com/nvidia/chirp links with github.com/lbliii/chirp: {offenders}"
    )


def test_public_chirp_docs_links_resolve_to_source_pages() -> None:
    """Absolute public docs links should resolve to pages in site/content/docs."""
    slugs = {_slug_from_path(path) for path in _site_markdown_files()}
    offenders: list[str] = []

    for rel_path in _public_markdown_files():
        path = _ROOT / rel_path
        for match in _CHIRP_DOC_LINK_RE.finditer(path.read_text()):
            url = match.group(0).rstrip(".,;:")
            slug = _slug_from_doc_link(url)
            if slug not in slugs:
                offenders.append(f"{rel_path}:{match.start()}: {url}")

    assert not offenders, f"Broken /chirp/docs links: {offenders}"


def test_public_docs_do_not_mark_markdown_filter_safe() -> None:
    """Markdown output is sanitized and marked safe by Chirp's filter."""
    offenders: list[str] = []
    for rel_path in _public_markdown_files():
        path = _ROOT / rel_path
        text = path.read_text()
        if _MARKDOWN_SAFE_PIPE_RE.search(text):
            offenders.append(str(rel_path))

    assert not offenders, (
        "Use `{{ content | markdown }}` in docs. `| safe` after markdown hides "
        f"the sanitizer contract: {offenders}"
    )
