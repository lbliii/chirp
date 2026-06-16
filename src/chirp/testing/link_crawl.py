"""Link-integrity crawl helpers for shell apps (#234).

``app.check()`` and ``TestClient`` string asserts validate contracts but cannot
prove that every ``href`` the shell renders resolves. These helpers render seed
pages, collect same-origin paths from the HTML, and GET each one — the cheap
deterministic counterpart to a full browser smoke.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

_HREF_RE = re.compile(r"""href\s*=\s*["']([^"']+)["']""", re.IGNORECASE)

_DEFAULT_SKIP_SUFFIXES: tuple[str, ...] = ("/stream",)
_EXTERNAL_PREFIXES: tuple[str, ...] = (
    "http://",
    "https://",
    "mailto:",
    "tel:",
    "javascript:",
    "data:",
)


def same_origin_paths(
    html: str,
    *,
    skip_static: bool = True,
    skip_suffixes: Iterable[str] = _DEFAULT_SKIP_SUFFIXES,
) -> set[str]:
    """Return crawlable same-origin paths embedded in ``html``.

    Strips ``#fragment`` anchors and query strings, drops external schemes,
    relative non-root paths, static assets (when ``skip_static=True``), and
    paths ending with any ``skip_suffixes`` entry (SSE streams, etc.).
    """
    paths: set[str] = set()
    suffixes = tuple(skip_suffixes)
    for raw in _HREF_RE.findall(html):
        href = raw.strip()
        if not href or href.startswith("#"):
            continue
        lower = href.lower()
        if lower.startswith(_EXTERNAL_PREFIXES):
            continue
        if not href.startswith("/"):
            continue
        path = href.split("#", 1)[0].split("?", 1)[0]
        if not path:
            continue
        if skip_static and path.startswith("/static/"):
            continue
        if any(path.endswith(suffix) for suffix in suffixes):
            continue
        paths.add(path)
    return paths


@dataclass(frozen=True, slots=True)
class LinkCrawlResult:
    """Outcome of a link-integrity crawl."""

    discovered: frozenset[str]
    broken: dict[str, int]

    @property
    def ok(self) -> bool:
        return not self.broken


async def crawl_links(
    client: Any,
    seed_pages: Iterable[str],
    *,
    headers: Mapping[str, str] | None = None,
    expected_status: int = 200,
    skip_static: bool = True,
    skip_suffixes: Iterable[str] = _DEFAULT_SKIP_SUFFIXES,
) -> LinkCrawlResult:
    """Render *seed_pages*, collect hrefs, and GET every discovered path.

    Returns a :class:`LinkCrawlResult` with the union of discovered paths and a
    ``broken`` map of ``path -> status`` for responses that did not match
    *expected_status*. Seed pages that fail to render raise ``AssertionError``.
    """
    hdrs = dict(headers or {})
    discovered: set[str] = set()
    for path in seed_pages:
        response = await client.get(path, headers=hdrs)
        if response.status != expected_status:
            msg = f"seed page {path!r} -> {response.status} (expected {expected_status})"
            raise AssertionError(msg)
        discovered |= same_origin_paths(
            response.text,
            skip_static=skip_static,
            skip_suffixes=skip_suffixes,
        )

    broken: dict[str, int] = {}
    for path in sorted(discovered):
        response = await client.get(path, headers=hdrs)
        if response.status != expected_status:
            broken[path] = response.status

    return LinkCrawlResult(frozenset(discovered), broken)


async def assert_link_integrity(
    client: Any,
    seed_pages: Iterable[str],
    *,
    headers: Mapping[str, str] | None = None,
    expected_status: int = 200,
    skip_static: bool = True,
    skip_suffixes: Iterable[str] = _DEFAULT_SKIP_SUFFIXES,
    require_links: bool = True,
) -> LinkCrawlResult:
    """Assert every same-origin link from *seed_pages* resolves.

    When *require_links* is true, an empty discovered set fails (guards against
    a vacuous crawl). Returns the :class:`LinkCrawlResult` on success.
    """
    result = await crawl_links(
        client,
        seed_pages,
        headers=headers,
        expected_status=expected_status,
        skip_static=skip_static,
        skip_suffixes=skip_suffixes,
    )
    if require_links and not result.discovered:
        raise AssertionError("no same-origin links discovered — crawl is vacuous")
    if result.broken:
        raise AssertionError(f"dead links (path -> status): {result.broken}")
    return result
