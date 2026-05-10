"""Static safety contracts for examples users copy into real apps."""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_EXAMPLES = _ROOT / "examples"

_MARKDOWN_SAFE_PIPE_RE = re.compile(r"\|\s*markdown\s*\|\s*safe\b")
_UNTRUSTED_FORWARDED_HEADER_RE = re.compile(r"request\.headers\.get\(\s*['\"]x-forwarded-for['\"]")


def _example_files(*suffixes: str) -> tuple[Path, ...]:
    suffix_set = set(suffixes)
    return tuple(sorted(path for path in _EXAMPLES.rglob("*") if path.suffix in suffix_set))


def test_examples_do_not_mark_markdown_filter_safe() -> None:
    """The Markdown filter returns sanitized Markup; examples should show that contract."""
    offenders = [
        str(path.relative_to(_ROOT))
        for path in _example_files(".html", ".md")
        if _MARKDOWN_SAFE_PIPE_RE.search(path.read_text())
    ]

    assert not offenders, (
        "Use `{{ content | markdown }}` in examples. `| safe` after markdown hides "
        f"the sanitizer contract: {offenders}"
    )


def test_examples_do_not_trust_unvalidated_forwarded_for_headers() -> None:
    """Examples should not teach spoofable client identity without a trusted proxy boundary."""
    offenders = [
        str(path.relative_to(_ROOT))
        for path in _example_files(".py")
        if _UNTRUSTED_FORWARDED_HEADER_RE.search(path.read_text())
    ]

    assert not offenders, (
        "Use request.client or explicit trusted-proxy middleware instead of directly "
        f"trusting x-forwarded-for in examples: {offenders}"
    )
