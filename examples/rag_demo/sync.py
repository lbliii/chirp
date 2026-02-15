"""Sync docs from Bengal index.json URLs into the RAG database.

Fetches index.json from configured URLs (e.g. vertical stack docs),
parses the pages array, and upserts into the docs table. Compatible
with Bengal's search index format.

Usage::

    RAG_DOC_SOURCES="https://lbliii.github.io/bengal/index.json,..." python app.py

Or call sync_from_sources(db, urls) from your startup.
"""

from __future__ import annotations

from collections.abc import Sequence
from urllib.parse import urljoin, urlparse

import httpx

from chirp.data import Database

# -- Types --


def _base_url(index_url: str) -> str:
    """Derive site base URL from index.json URL.

    https://lbliii.github.io/bengal/index.json -> https://lbliii.github.io
    """
    parsed = urlparse(index_url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _full_url(base: str, href: str) -> str:
    """Build absolute URL from base and href.

    href is typically absolute path like /bengal/foo/
    """
    return urljoin(base.rstrip("/") + "/", href)


def _extract_content(page: dict) -> str:
    """Extract searchable text from a page entry.

    Prefer content > excerpt > description. Skip empty.
    """
    for key in ("content", "excerpt", "description"):
        val = page.get(key)
        if val and isinstance(val, str) and val.strip():
            return val.strip()
    return ""


async def fetch_index(index_url: str) -> list[dict]:
    """Fetch and parse index.json from a URL.

    Returns the pages array. Raises on HTTP errors or invalid JSON.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(index_url)
        resp.raise_for_status()
        data = resp.json()
    pages = data.get("pages", data) if isinstance(data, dict) else data
    return pages if isinstance(pages, list) else []


async def sync_from_url(db: Database, index_url: str) -> int:
    """Sync docs from a single index.json URL.

    Deletes existing docs from this source, then inserts all pages
    with non-empty content. Returns number of docs inserted.

    Requires db to have docs table with (title, content, url, source).
    """
    pages = await fetch_index(index_url)
    base = _base_url(index_url)
    rows: list[tuple[str, str, str, str]] = []

    for p in pages:
        if not isinstance(p, dict):
            continue
        content = _extract_content(p)
        if not content or len(content) < 10:
            continue
        title = p.get("title") or p.get("objectID") or "Untitled"
        if not isinstance(title, str):
            title = str(title)
        href = p.get("href") or p.get("url") or p.get("uri") or "/"
        url = _full_url(base, href) if isinstance(href, str) else str(href)
        rows.append((title, content, url, index_url))

    if not rows:
        return 0

    async with db.transaction():
        await db.execute("DELETE FROM docs WHERE source = ?", index_url)
        await db.execute_many(
            "INSERT INTO docs (title, content, url, source) VALUES (?, ?, ?, ?)",
            rows,
        )
    return len(rows)


async def sync_from_sources(db: Database, urls: Sequence[str]) -> dict[str, int]:
    """Sync docs from multiple index.json URLs.

    Returns mapping of url -> count of docs inserted.
    """
    result: dict[str, int] = {}
    for url in urls:
        url = url.strip()
        if not url:
            continue
        try:
            count = await sync_from_url(db, url)
            result[url] = count
        except Exception as e:
            result[url] = -1
            # Log but don't fail — other sources may succeed
            print(f"[rag_demo] sync failed {url}: {e}", flush=True)
    return result
