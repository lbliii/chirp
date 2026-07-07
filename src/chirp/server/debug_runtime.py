"""Native debug runtime wiring and trace storage."""

from __future__ import annotations

import json
import time
from collections import deque
from dataclasses import asdict, dataclass
from threading import Lock
from typing import Any

from chirp.app.state import (
    DebugInjectionSpec,
    InternalFeatureSpec,
    InternalRouteSpec,
    RuntimeDebugWiring,
)
from chirp.config import AppConfig
from chirp.server.dev_browser_reload import (
    DEV_BROWSER_RELOAD_SNIPPET,
    DEV_RELOAD_SSE_PATH,
    is_dev_browser_reload_enabled,
)
from chirp.server.devtools import DEVTOOLS_BOOT_PATH, DEVTOOLS_BOOT_SNIPPET, HIGHLIGHT_PATH
from chirp.server.fragment_dispatch import FRAGMENT_ROUTE_PREFIX
from chirp.server.fragment_targets_debug import FRAGMENT_TARGETS_DEBUG_PATH
from chirp.server.route_explorer import ROUTE_EXPLORER_PATH

DEBUG_MANIFEST_PATH = "/__chirp/debug/manifest.json"
DEBUG_TRACES_PATH = "/__chirp/debug/traces.json"


@dataclass(frozen=True, slots=True)
class DebugTraceRecord:
    """One bounded debug trace record."""

    channel: str
    phase: str
    path: str
    request_id: str
    internal: bool
    owner: str
    ts_ms: int
    data: dict[str, Any]


class DebugTraceStore:
    """Thread-safe bounded in-memory trace buffer for debug mode."""

    __slots__ = ("_items", "_limit", "_lock")

    def __init__(self, limit: int = 500) -> None:
        self._limit = limit
        self._items: deque[DebugTraceRecord] = deque(maxlen=limit)
        self._lock = Lock()

    def record_sse(
        self,
        *,
        phase: str,
        path: str,
        request_id: str,
        internal: bool,
        owner: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        """Record an SSE lifecycle event without mutating stream output."""
        self._record(
            channel="sse",
            phase=phase,
            path=path,
            request_id=request_id,
            internal=internal,
            owner=owner,
            data=data,
        )

    def record_http(
        self,
        *,
        phase: str,
        path: str,
        request_id: str,
        internal: bool,
        owner: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        """Record one bounded HTTP render observation."""
        self._record(
            channel="http",
            phase=phase,
            path=path,
            request_id=request_id,
            internal=internal,
            owner=owner,
            data=data,
        )

    def _record(
        self,
        *,
        channel: str,
        phase: str,
        path: str,
        request_id: str,
        internal: bool,
        owner: str,
        data: dict[str, Any] | None,
    ) -> None:
        record = DebugTraceRecord(
            channel=channel,
            phase=phase,
            path=path,
            request_id=request_id,
            internal=internal,
            owner=owner,
            ts_ms=time.time_ns() // 1_000_000,
            data=data or {},
        )
        with self._lock:
            self._items.append(record)

    def records(self, *, include_internal: bool = False) -> tuple[DebugTraceRecord, ...]:
        """Return a stable snapshot of buffered records."""
        with self._lock:
            items = tuple(self._items)
        if include_internal:
            return items
        return tuple(item for item in items if not item.internal)


def build_runtime_debug_wiring(config: AppConfig) -> RuntimeDebugWiring:
    """Build the immutable internal/debug wiring descriptor for an app."""
    dev_reload_enabled = bool(config.debug and is_dev_browser_reload_enabled(config))
    devtools_enabled = bool(config.debug)
    routes = (
        InternalRouteSpec(
            path=FRAGMENT_ROUTE_PREFIX,
            owner="fragment_dispatch",
            kind="dispatcher",
            transport="html",
            enabled=True,
            visibility="hidden",
            reserved_prefix=FRAGMENT_ROUTE_PREFIX,
        ),
        InternalRouteSpec(
            path=DEVTOOLS_BOOT_PATH,
            owner="devtools",
            kind="asset",
            transport="javascript",
            enabled=devtools_enabled,
            visibility="hidden",
            reserved_prefix="/__chirp/debug",
        ),
        InternalRouteSpec(
            path=HIGHLIGHT_PATH,
            owner="devtools",
            kind="api",
            transport="json",
            enabled=devtools_enabled,
            visibility="internal",
        ),
        InternalRouteSpec(
            path=FRAGMENT_TARGETS_DEBUG_PATH,
            owner="devtools",
            kind="api",
            transport="json",
            enabled=devtools_enabled,
            visibility="internal",
        ),
        InternalRouteSpec(
            path=DEBUG_MANIFEST_PATH,
            owner="devtools",
            kind="api",
            transport="json",
            enabled=devtools_enabled,
            visibility="hidden",
        ),
        InternalRouteSpec(
            path=DEBUG_TRACES_PATH,
            owner="devtools",
            kind="api",
            transport="json",
            enabled=devtools_enabled,
            visibility="hidden",
        ),
        InternalRouteSpec(
            path=ROUTE_EXPLORER_PATH,
            owner="route_explorer",
            kind="page",
            transport="html",
            enabled=devtools_enabled,
            visibility="internal",
        ),
        InternalRouteSpec(
            path=DEV_RELOAD_SSE_PATH,
            owner="dev_browser_reload",
            kind="sse",
            transport="sse",
            enabled=dev_reload_enabled,
            visibility="hidden",
            reserved_prefix="/__chirp__",
        ),
    )
    devtools_injections: tuple[DebugInjectionSpec, ...] = ()
    if devtools_enabled:
        devtools_injections = (
            DebugInjectionSpec(
                name="devtools_boot",
                snippet=DEVTOOLS_BOOT_SNIPPET,
                asset_path=DEVTOOLS_BOOT_PATH,
                skip_htmx=True,
            ),
        )
    reload_injections: tuple[DebugInjectionSpec, ...] = ()
    if dev_reload_enabled:
        reload_injections = (
            DebugInjectionSpec(
                name="dev_browser_reload",
                snippet=DEV_BROWSER_RELOAD_SNIPPET,
                asset_path=DEV_RELOAD_SSE_PATH,
                full_page_only=True,
                skip_htmx=True,
            ),
        )
    features = (
        InternalFeatureSpec(
            name="devtools",
            enabled=devtools_enabled,
            reason="debug enabled" if devtools_enabled else "debug disabled",
            route_paths=(
                DEVTOOLS_BOOT_PATH,
                HIGHLIGHT_PATH,
                FRAGMENT_TARGETS_DEBUG_PATH,
                DEBUG_MANIFEST_PATH,
                DEBUG_TRACES_PATH,
                ROUTE_EXPLORER_PATH,
            ),
            injections=devtools_injections,
        ),
        InternalFeatureSpec(
            name="dev_browser_reload",
            enabled=dev_reload_enabled,
            reason="reload enabled" if dev_reload_enabled else "reload disabled",
            route_paths=(DEV_RELOAD_SSE_PATH,),
            injections=reload_injections,
        ),
    )
    return RuntimeDebugWiring(
        routes=routes,
        features=features,
        trace_store=DebugTraceStore() if config.debug else None,
    )


def render_debug_manifest_json(wiring: RuntimeDebugWiring) -> str:
    """Serialize debug wiring for the browser DevTools runtime."""
    return json.dumps(
        {
            "routes": [asdict(route) for route in wiring.routes],
            "features": [
                {
                    "name": feature.name,
                    "enabled": feature.enabled,
                    "reason": feature.reason,
                    "route_paths": list(feature.route_paths),
                    "injections": [
                        {
                            "name": injection.name,
                            "asset_path": injection.asset_path,
                            "before": injection.before,
                            "full_page_only": injection.full_page_only,
                            "skip_htmx": injection.skip_htmx,
                        }
                        for injection in feature.injections
                    ],
                }
                for feature in wiring.features
            ],
        },
        sort_keys=True,
    )


def render_debug_traces_json(
    wiring: RuntimeDebugWiring,
    *,
    include_internal: bool = False,
) -> str:
    """Serialize buffered debug traces."""
    store = wiring.trace_store
    records = store.records(include_internal=include_internal) if store is not None else ()
    return json.dumps(
        {"records": [asdict(record) for record in records]},
        sort_keys=True,
    )
