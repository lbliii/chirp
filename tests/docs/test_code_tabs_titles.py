"""Guards for Bengal code-tabs fences missing distinct titles (#358)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_SITE_DOCS = _ROOT / "site" / "content" / "docs"
_CODE_TABS_OPEN_RE = re.compile(r":{3,4}\{code-tabs\}")


def _site_markdown_files() -> tuple[Path, ...]:
    if not _SITE_DOCS.is_dir():
        pytest.skip("site/content/docs/ not found")
    return tuple(sorted(_SITE_DOCS.rglob("*.md")))


def _untitled_fences_in_code_tabs(text: str) -> list[str]:
    offenders: list[str] = []
    for block in _CODE_TABS_OPEN_RE.split(text)[1:]:
        end = block.find(":::")
        chunk = block[:end] if end >= 0 else block
        fences = re.findall(r"```(\w+)([^\n]*)\n", chunk)
        if len(fences) < 2:
            continue
        for lang, meta in fences:
            if "title=" not in meta:
                offenders.append(f"{lang} fence missing title= in multi-tab group")
    return offenders


@pytest.mark.issue(358)
def test_code_tabs_groups_with_multiple_fences_have_titles() -> None:
    """Multi-fence code-tabs must carry title= so Bengal tabs stay distinct/selectable."""
    offenders: list[str] = []
    for path in _site_markdown_files():
        rel = path.relative_to(_ROOT)
        offenders.extend(
            f"{rel}: {msg}"
            for msg in _untitled_fences_in_code_tabs(path.read_text(encoding="utf-8"))
        )

    assert not offenders, (
        f'Add title="..." to each fence in code-tabs groups with 2+ tabs. Offenders: {offenders}'
    )
