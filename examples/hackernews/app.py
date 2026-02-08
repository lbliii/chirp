"""Hacker News Live Reader — real API, real-time updates, zero JavaScript.

Consumes the free HN Firebase API. Stories load on the initial page,
scores and comment counts update in real-time via SSE, and comment
trees render recursively using kida's ``{% def %}``.

Run:
    pip install httpx  # (or pip install chirp[all])
    python app.py
"""

import asyncio
import contextvars
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx

from chirp import App, AppConfig, EventStream, Fragment, Page, Template

TEMPLATES_DIR = Path(__file__).parent / "templates"

config = AppConfig(template_dir=TEMPLATES_DIR)
app = App(config=config)

# ---------------------------------------------------------------------------
# Data models — frozen for free-threading safety
# ---------------------------------------------------------------------------

HN_BASE = "https://hacker-news.firebaseio.com/v0/"


@dataclass(frozen=True, slots=True)
class Story:
    id: int
    title: str
    url: str
    score: int
    by: str
    time: int
    descendants: int
    domain: str


@dataclass(frozen=True, slots=True)
class Comment:
    id: int
    text: str
    by: str
    time: int
    kids: tuple[int, ...]
    replies: tuple["Comment", ...]


# ---------------------------------------------------------------------------
# Thread-safe state
# ---------------------------------------------------------------------------

_stories: dict[int, Story] = {}
_story_ids: list[int] = []
_lock = threading.Lock()

# Per-worker httpx client.  Each pounce worker thread runs its own asyncio
# event loop, so each worker creates its own client via on_worker_startup.
_client_var: contextvars.ContextVar[httpx.AsyncClient | None] = contextvars.ContextVar(
    "hn_client", default=None,
)


# ---------------------------------------------------------------------------
# Seed data — provides initial content for instant page load and offline tests
# ---------------------------------------------------------------------------

_SEED_STORIES = [
    Story(
        id=1, title="Show HN: Chirp – A Python web framework for the modern web",
        url="https://github.com/example/chirp", score=142, by="builder",
        time=0, descendants=37, domain="github.com",
    ),
    Story(
        id=2, title="Free-threading lands in Python 3.14",
        url="https://docs.python.org/3.14/whatsnew/3.14.html", score=89,
        by="pythonista", time=0, descendants=23, domain="docs.python.org",
    ),
    Story(
        id=3, title="HTML Over the Wire: A Modern Approach",
        url="https://htmx.org/essays/hypermedia-systems/", score=67,
        by="webdev", time=0, descendants=15, domain="htmx.org",
    ),
]


def _seed() -> None:
    """Populate the cache with seed data for instant first render."""
    import time as _time

    now = int(_time.time())
    with _lock:
        for i, s in enumerate(_SEED_STORIES):
            story = Story(
                id=s.id, title=s.title, url=s.url, score=s.score,
                by=s.by, time=now - (i * 3600), descendants=s.descendants,
                domain=s.domain,
            )
            _stories[story.id] = story
            _story_ids.append(story.id)


# Seed on module load so the first page render always has content
_seed()


def _extract_domain(url: str) -> str:
    """Extract display domain from a URL (e.g. 'github.com')."""
    if not url:
        return ""
    try:
        host = urlparse(url).netloc
        return host.removeprefix("www.")
    except Exception:
        return ""


def _parse_story(data: dict) -> Story:
    """Convert raw HN API JSON into a Story."""
    url = data.get("url", "")
    return Story(
        id=data["id"],
        title=data.get("title", "(untitled)"),
        url=url,
        score=data.get("score", 0),
        by=data.get("by", "unknown"),
        time=data.get("time", 0),
        descendants=data.get("descendants", 0),
        domain=_extract_domain(url),
    )


def _get_stories(count: int = 30) -> list[Story]:
    """Return a snapshot of the top N cached stories in order."""
    with _lock:
        return [_stories[sid] for sid in _story_ids[:count] if sid in _stories]


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


async def _fetch_item(item_id: int) -> dict | None:
    """Fetch a single item from the HN API. Returns None on failure."""
    client = _client_var.get()
    if client is None:
        return None
    try:
        resp = await client.get(f"item/{item_id}.json")
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, dict) else None
    except (httpx.HTTPError, ValueError):
        return None


async def _fetch_stories(count: int = 30) -> list[Story]:
    """Fetch top story IDs then fetch each story concurrently."""
    client = _client_var.get()
    if client is None:
        return []
    try:
        resp = await client.get("topstories.json")
        resp.raise_for_status()
        ids = resp.json()
    except (httpx.HTTPError, ValueError):
        return []

    ids = ids[:count]
    stories: list[Story] = []
    # Fetch stories concurrently in batches
    tasks = [_fetch_item(sid) for sid in ids]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for data in results:
        if isinstance(data, dict) and data.get("type") == "story":
            stories.append(_parse_story(data))
    return stories


async def _refresh_stories(count: int = 30) -> None:
    """Refresh the story cache from the HN API."""
    stories = await _fetch_stories(count)
    if not stories:
        return
    with _lock:
        _story_ids.clear()
        for story in stories:
            _stories[story.id] = story
            _story_ids.append(story.id)


async def _fetch_comment_tree(comment_id: int, depth: int = 3) -> Comment | None:
    """Recursively fetch a comment and its replies up to a depth limit."""
    data = await _fetch_item(comment_id)
    if data is None or data.get("type") != "comment":
        return None

    kids = tuple(data.get("kids", ()))
    replies: tuple[Comment, ...] = ()

    if depth > 0 and kids:
        tasks = [_fetch_comment_tree(kid, depth - 1) for kid in kids[:10]]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        replies = tuple(r for r in results if isinstance(r, Comment))

    return Comment(
        id=data["id"],
        text=data.get("text", ""),
        by=data.get("by", "[deleted]"),
        time=data.get("time", 0),
        kids=kids,
        replies=replies,
    )


# ---------------------------------------------------------------------------
# Lifecycle hooks
# ---------------------------------------------------------------------------


@app.on_worker_startup
async def worker_startup() -> None:
    """Create an httpx client for this worker's event loop.

    Each pounce worker thread gets its own event loop.  httpx's
    connection pool binds asyncio primitives to the loop where the
    client is created, so we create one client per worker here.
    """
    _client_var.set(httpx.AsyncClient(base_url=HN_BASE, timeout=10.0))

    # Pre-populate the story cache on the first worker that runs.
    # Seed data from module load is already available, so a network
    # failure here is non-fatal.
    try:
        await _refresh_stories()
    except Exception:
        pass  # seed data is already loaded


@app.on_worker_shutdown
async def worker_shutdown() -> None:
    """Close the httpx client for this worker."""
    client = _client_var.get()
    if client:
        await client.aclose()
        _client_var.set(None)


# ---------------------------------------------------------------------------
# Template filters
# ---------------------------------------------------------------------------


@app.template_filter("timeago")
def timeago(unix_ts: int) -> str:
    """Convert a unix timestamp to a human-readable relative time."""
    if not unix_ts:
        return ""
    delta = int(time.time()) - unix_ts
    if delta < 60:
        return "just now"
    if delta < 3600:
        m = delta // 60
        return f"{m} minute{'s' if m != 1 else ''} ago"
    if delta < 86400:
        h = delta // 3600
        return f"{h} hour{'s' if h != 1 else ''} ago"
    d = delta // 86400
    return f"{d} day{'s' if d != 1 else ''} ago"


@app.template_filter("pluralize")
def pluralize(count: int, singular: str, plural: str | None = None) -> str:
    """Pluralize a word based on count. Usage: {{ n | pluralize('comment') }}"""
    if plural is None:
        plural = singular + "s"
    word = singular if count == 1 else plural
    return f"{count} {word}"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.route("/")
def index():
    """Front page — top 30 stories from Hacker News."""
    stories = _get_stories(30)
    return Page("hackernews.html", "story_list", stories=stories, page="list")


@app.route("/story/{story_id}")
async def story_detail(story_id: int):
    """Story detail page with threaded comments."""
    # Fetch fresh story data
    data = await _fetch_item(story_id)
    if data is None:
        return Template("hackernews.html", stories=[], page="list")

    story = _parse_story(data)

    # Fetch comment tree
    kid_ids = data.get("kids", [])[:20]
    tasks = [_fetch_comment_tree(kid, depth=2) for kid in kid_ids]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    comments = [r for r in results if isinstance(r, Comment)]

    return Page(
        "hackernews.html", "story_detail",
        story=story, comments=comments, page="detail",
    )


@app.route("/events")
def events():
    """Live score and comment-count updates via Server-Sent Events.

    Polls the HN API every ~5 seconds for the visible stories and pushes
    OOB fragment updates when score or comment count changes.
    """

    async def generate():
        # Yield the first cached story immediately so the SSE pipeline
        # is testable without network access (and the browser sees a
        # quick confirmation that the connection is alive).
        stories = _get_stories(1)
        if stories:
            yield Fragment("hackernews.html", "story_meta", story=stories[0])

        while True:
            with _lock:
                ids = list(_story_ids[:30])
            for story_id in ids:
                data = await _fetch_item(story_id)
                if data is None:
                    continue
                with _lock:
                    old = _stories.get(story_id)
                if old is None:
                    continue
                new_score = data.get("score", 0)
                new_descendants = data.get("descendants", 0)
                if new_score != old.score or new_descendants != old.descendants:
                    updated = Story(
                        id=old.id,
                        title=old.title,
                        url=old.url,
                        score=new_score,
                        by=old.by,
                        time=old.time,
                        descendants=new_descendants,
                        domain=old.domain,
                    )
                    with _lock:
                        _stories[story_id] = updated
                    yield Fragment(
                        "hackernews.html", "story_meta", story=updated
                    )
            await asyncio.sleep(5)

    return EventStream(generate())


# ---------------------------------------------------------------------------
# Entry point — multi-worker Pounce for the full demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        from pounce.config import ServerConfig
        from pounce.server import Server

        app._ensure_frozen()
        server_config = ServerConfig(host="127.0.0.1", port=8000, workers=4)
        server = Server(server_config, app)
        print("Hacker News Live Reader")
        print("  http://127.0.0.1:8000")
        print("  4 worker threads (free-threading)")
        print()
        server.run()
    except ImportError:
        # Pounce not installed — fall back to single-worker dev server
        print("Hacker News Live Reader (single worker — install pounce for multi-worker)")
        app.run()
