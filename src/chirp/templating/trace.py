"""Typed return diagnostics for DevTools and debug headers."""

from __future__ import annotations

import base64
import json
from dataclasses import asdict, dataclass
from typing import Any

from chirp.http.request import Request

RETURN_TRACE_CACHE_KEY = "_chirp_return_trace"


@dataclass(frozen=True, slots=True)
class ReturnTrace:
    """Bounded, server-owned diagnostic for a typed route return."""

    return_type: str
    category: str
    is_htmx: bool
    render_intent: str = "unknown"
    status: int | None = None
    template: str | None = None
    block: str | None = None
    target: str | None = None
    swap: str | None = None
    context_keys: tuple[str, ...] = ()
    streaming: bool = False
    sse: bool = False
    notes: tuple[str, ...] = ()

    def payload(self) -> dict[str, Any]:
        """Return a JSON-serializable payload."""
        data = asdict(self)
        data["context_keys"] = list(self.context_keys)
        data["notes"] = list(self.notes)
        return data


def stash_return_trace_for_request(trace: ReturnTrace, request: Request | None) -> None:
    """Store a return trace on the current request."""
    if request is None:
        return
    request._cache[RETURN_TRACE_CACHE_KEY] = trace


def get_return_trace(request: Any) -> ReturnTrace | None:
    """Return the stashed typed return trace, if present."""
    cache = getattr(request, "_cache", None)
    if not isinstance(cache, dict):
        return None
    trace = cache.get(RETURN_TRACE_CACHE_KEY)
    return trace if isinstance(trace, ReturnTrace) else None


def encode_return_trace(trace: ReturnTrace) -> str:
    """Encode a return trace for a compact debug response header."""
    raw = json.dumps(trace.payload(), separators=(",", ":"), sort_keys=True).encode()
    return base64.b64encode(raw).decode("ascii")
