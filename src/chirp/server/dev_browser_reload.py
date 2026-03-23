"""Browser live reload for development (SSE + mtime polling).

No extra dependencies: polls file mtimes on an interval and emits ``reload``
events. Works alongside Pounce's Python ``--reload`` so .py changes restart
the process while .html/.css edits trigger an in-browser refresh.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import TYPE_CHECKING

from chirp.app.state import PendingRoute
from chirp.realtime.events import EventStream, SSEEvent

if TYPE_CHECKING:
    from chirp.config import AppConfig

# Stable path unlikely to collide with user routes
DEV_RELOAD_SSE_PATH = "/__chirp__/dev-reload"

DEV_BROWSER_RELOAD_SNIPPET = f"""\
<script>
(function() {{
  var es = new EventSource("{DEV_RELOAD_SSE_PATH}");
  es.addEventListener("reload", function() {{ location.reload(); }});
  es.onerror = function() {{ setTimeout(function() {{ location.reload(); }}, 2000); }};
}})();
</script>"""


def _watch_roots(config: AppConfig) -> list[Path]:
    """Directories to scan for template/static changes."""
    roots: list[Path] = []
    cwd = Path.cwd().resolve()
    roots.append(cwd)

    td = config.template_dir
    if td:
        p = Path(td)
        if not p.is_absolute():
            p = cwd / p
        p = p.resolve()
        if p.is_dir():
            roots.append(p)

    sd = config.static_dir
    if sd:
        p = Path(sd)
        if not p.is_absolute():
            p = cwd / p
        p = p.resolve()
        if p.is_dir():
            roots.append(p)

    for extra in config.reload_dirs:
        p = Path(extra)
        if not p.is_absolute():
            p = cwd / p
        p = p.resolve()
        if p.is_dir():
            roots.append(p)

    # De-dupe preserving order
    seen: set[Path] = set()
    out: list[Path] = []
    for r in roots:
        if r not in seen:
            seen.add(r)
            out.append(r)
    return out


_SKIP_DIRS = frozenset((".git", ".venv", "venv", "node_modules", "__pycache__", ".mypy_cache"))


def _iter_tracked_files(roots: list[Path], suffixes: tuple[str, ...]) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        for suffix in suffixes:
            files.extend(
                p
                for p in root.rglob(f"*{suffix}")
                if not any(part in _SKIP_DIRS for part in p.parts)
            )
    return files


async def _reload_event_stream(
    config: AppConfig,
) -> AsyncIterator[SSEEvent]:
    """Yield SSE reload events when watched files change."""
    roots = _watch_roots(config)
    suffixes = tuple(x.lower() for x in config.reload_include)
    if not suffixes:
        return
    mtimes: dict[str, float] = {}
    tracked_files: list[Path] = []
    tick = 0
    # Re-scan the tree periodically so new files are picked up; avoid rglob every tick.
    rescan_every = 48  # ~21s at 0.45s sleep

    while True:
        await asyncio.sleep(0.45)
        tick += 1
        if tick % rescan_every == 1 or not tracked_files:
            tracked_files = _iter_tracked_files(roots, suffixes)
        changed = False
        for path in tracked_files:
            key = str(path.resolve())
            try:
                m = path.stat().st_mtime
            except OSError:
                continue
            old = mtimes.get(key)
            if old is None:
                mtimes[key] = m
            elif m > old:
                mtimes[key] = m
                changed = True
        if changed:
            yield SSEEvent(data="reload", event="reload")


def make_dev_reload_pending_route(config: AppConfig) -> PendingRoute:
    """Return a pending route for the dev-reload SSE stream."""

    def _handler() -> EventStream:
        return EventStream(_reload_event_stream(config))

    return PendingRoute(
        DEV_RELOAD_SSE_PATH,
        _handler,
        ["GET"],
        name="chirp_dev_browser_reload",
        referenced=True,
    )
