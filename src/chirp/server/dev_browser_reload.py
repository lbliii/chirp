"""Browser live reload for development (SSE + mtime polling).

No extra dependencies: polls file mtimes on an interval and emits ``reload``
events. Works alongside Pounce's Python ``--reload`` so .py changes restart
the process while .html/.css edits trigger an in-browser refresh.
"""

from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import AsyncIterator
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from chirp.app.state import PendingRoute, RuntimeAppState
from chirp.realtime.events import EventStream, SSEEvent

if TYPE_CHECKING:
    from chirp.config import AppConfig
    from chirp.templating.dev_template_reload import (
        TemplateReloadPlan,
        TemplateReloadPlanner,
        TemplateReloadSurface,
    )
    from chirp.templating.fragment_target_registry import FragmentTargetRegistry

# Stable path unlikely to collide with user routes
DEV_RELOAD_SSE_PATH = "/__chirp__/dev-reload"


class _TemplateReloadPlannerLike(Protocol):
    def plan_edit(
        self,
        filename: str | Path,
        surface: TemplateReloadSurface,
    ) -> TemplateReloadPlan: ...


class _TemplateReloadPlanPublisher:
    """Publish one stable plan per file revision across reload connections."""

    __slots__ = ("_cache", "_lock", "_planner")

    def __init__(self, planner: TemplateReloadPlanner) -> None:
        self._planner = planner
        self._lock = threading.Lock()
        self._cache: dict[
            str,
            tuple[tuple[int, int] | None, TemplateReloadSurface, TemplateReloadPlan],
        ] = {}

    def plan_edit(
        self,
        filename: str | Path,
        surface: TemplateReloadSurface,
    ) -> TemplateReloadPlan:
        path = Path(filename)
        key = str(path.resolve())
        try:
            stat = path.stat()
            fingerprint: tuple[int, int] | None = (stat.st_mtime_ns, stat.st_size)
        except OSError:
            fingerprint = None
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None and cached[:2] == (fingerprint, surface):
                return cached[2]
            plan = self._planner.plan_edit(path, surface)
            if key not in self._cache and len(self._cache) >= 256:
                self._cache.pop(next(iter(self._cache)))
            self._cache[key] = (fingerprint, surface, plan)
            return plan


DEV_BROWSER_RELOAD_SNIPPET = f"""\
<script>
(function() {{
  if (window.__chirpDevReloadBooted) return;
  window.__chirpDevReloadBooted = true;
  if (window.__chirpDevReloadSource && window.__chirpDevReloadSource.close) {{
    try {{ window.__chirpDevReloadSource.close(); }} catch (e) {{}}
  }}
  var es = new EventSource("{DEV_RELOAD_SSE_PATH}");
  window.__chirpDevReloadSource = es;
  es.addEventListener("planner", function(evt) {{
    try {{
      var detail = JSON.parse(evt.data || "null");
      if (detail && typeof detail === "object") {{
        window.dispatchEvent(new CustomEvent("chirp:reload-plan", {{ detail: detail }}));
      }}
    }} catch (e) {{}}
  }});
  es.addEventListener("reload", function() {{ location.reload(); }});
  es.addEventListener("css", function() {{
    var t = Date.now();
    document.querySelectorAll('link[rel="stylesheet"]').forEach(function(l) {{
      var href = l.getAttribute("href");
      if (href) {{ l.setAttribute("href", href.split("?")[0] + "?_cr=" + t); }}
    }});
  }});
  es.onerror = function() {{ setTimeout(function() {{ location.reload(); }}, 2000); }};
}})();
</script>"""


def is_dev_browser_reload_enabled(config: AppConfig) -> bool:
    """Return whether dev browser reload should register browser-visible wiring."""
    return bool(config.dev_browser_reload and config.reload_include)


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

    for cdir in config.component_dirs:
        p = Path(cdir)
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
    planner: _TemplateReloadPlannerLike | None = None,
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
        changed_suffixes: set[str] = set()
        changed_paths: list[Path] = []
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
                changed_suffixes.add(path.suffix.lower())
                changed_paths.append(path)
        if changed_suffixes:
            for event in _template_reload_plan_events(changed_paths, planner):
                yield event
            if changed_suffixes <= {".css"}:
                yield SSEEvent(data="css", event="css")
            else:
                yield SSEEvent(data="reload", event="reload")


def _template_reload_plan_events(
    changed_paths: list[Path],
    planner: _TemplateReloadPlannerLike | None,
) -> tuple[SSEEvent, ...]:
    """Return redacted planner records for changed HTML before full reload."""
    if planner is None:
        return ()
    from chirp.templating.dev_template_reload import TemplateReloadSurface

    surface = TemplateReloadSurface()
    events = []
    for path in sorted(set(changed_paths)):
        if path.suffix.lower() != ".html":
            continue
        events.append(_template_reload_plan_event(planner.plan_edit(path, surface)))
    return tuple(events)


def _template_reload_plan_event(plan: TemplateReloadPlan) -> SSEEvent:
    """Serialize only the public-safe fields approved for DevTools."""
    payload = {
        "schema_version": 1,
        "revision": plan.revision,
        "outcome": plan.outcome,
        "reason": plan.reason,
        "template_name": plan.template_name,
        "changed_blocks": list(plan.changed_blocks),
        "added_blocks": list(plan.added_blocks),
        "removed_blocks": list(plan.removed_blocks),
        "target_id": plan.target_id,
        "error_type": plan.error_type,
        "error_line": plan.error_line,
        "requires_response_validation": plan.requires_response_validation,
    }
    return SSEEvent(
        data=json.dumps(payload, sort_keys=True, separators=(",", ":")),
        event="planner",
    )


def _build_template_reload_planner(
    runtime_state: RuntimeAppState | None,
    fragment_targets: FragmentTargetRegistry | None,
) -> _TemplateReloadPlannerLike | None:
    """Build the shared planner lazily after app freeze publishes its graph."""
    if runtime_state is None:
        return None
    env = runtime_state.kida_env
    if env is None:
        return None
    from chirp.templating.dev_template_reload import (
        TemplateReloadPlanner,
        build_template_reload_inventory,
    )

    inventory = build_template_reload_inventory(
        env,
        runtime_state.hypermedia_program,
        fragment_targets,
    )
    return _TemplateReloadPlanPublisher(TemplateReloadPlanner(env, inventory))


def make_dev_reload_pending_route(
    config: AppConfig,
    runtime_state: RuntimeAppState | None = None,
    fragment_targets: FragmentTargetRegistry | None = None,
) -> PendingRoute:
    """Return a pending route for the dev-reload SSE stream."""
    planner: _TemplateReloadPlannerLike | None = None
    planner_ready = False
    planner_lock = threading.Lock()

    def _planner() -> _TemplateReloadPlannerLike | None:
        nonlocal planner, planner_ready
        with planner_lock:
            if not planner_ready:
                planner = _build_template_reload_planner(runtime_state, fragment_targets)
                planner_ready = True
            return planner

    def _handler() -> EventStream:
        return EventStream(_reload_event_stream(config, _planner()))

    return PendingRoute(
        DEV_RELOAD_SSE_PATH,
        _handler,
        ["GET"],
        name="chirp_dev_browser_reload",
        referenced=True,
    )
