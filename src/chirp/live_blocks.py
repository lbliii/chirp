"""Live-block declarations for hybrid static/dynamic freeze output.

A *live block* is a named template block on a frozen page that is swapped out
at freeze time for an htmx placeholder. At request time the placeholder hits
the block-fetch dispatcher (``/_frag{path}?_b={block}``) and the declared
handler renders the block dynamically.

Declarations are registered via :func:`chirp.App.live_block` and stored in
``MutableAppState.live_blocks`` keyed by ``(route, block)``. The freeze
pipeline consults this map during post-processing; the dispatcher uses the
same map to resolve which handler to invoke (falling back to the route's
native handler when the live-block handler is the same as the route's).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class LiveBlockSpec:
    """Declaration of one live block on one route."""

    route: str
    block: str
    handler: Callable[..., Awaitable[Any] | Any]
    trigger: str = "load"
    swap: str = "innerHTML"
    skeleton: str | None = None
    cache_seconds: int | None = None
