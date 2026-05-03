"""Guards for stale public docs links."""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_SITE_DOCS = _ROOT / "site" / "content" / "docs"


def _site_markdown_files() -> tuple[Path, ...]:
    return tuple(sorted(_SITE_DOCS.rglob("*.md")))


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
