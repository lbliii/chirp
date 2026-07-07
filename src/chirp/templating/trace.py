"""Typed return diagnostics for DevTools and debug headers."""

from __future__ import annotations

import base64
import json
from dataclasses import asdict, dataclass
from typing import Any

from chirp.http.request import Request

RETURN_TRACE_CACHE_KEY = "_chirp_return_trace"

_MAX_CONTEXT_KEYS = 48
_MAX_NOTES = 16
_MAX_NOTE_LENGTH = 240
_MAX_TRANSITIONS = 16
_MAX_ID_LENGTH = 512


def _bounded(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[: limit - 3] + "..."


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
    route_id: str | None = None
    route_path: str | None = None
    observation_id: str | None = None
    request_mode: str | None = None
    mode_tags: tuple[str, ...] = ()
    compiled_transition_ids: tuple[str, ...] = ()
    transition_descriptions: tuple[str, ...] = ()

    def payload(self) -> dict[str, Any]:
        """Return a JSON-serializable payload."""
        data = asdict(self)
        for name in (
            "template",
            "block",
            "target",
            "route_id",
            "route_path",
            "observation_id",
        ):
            value = data[name]
            if isinstance(value, str):
                data[name] = _bounded(value, _MAX_ID_LENGTH)
        data["context_keys"] = [
            _bounded(key, _MAX_NOTE_LENGTH) for key in self.context_keys[:_MAX_CONTEXT_KEYS]
        ]
        data["notes"] = [_bounded(note, _MAX_NOTE_LENGTH) for note in self.notes[:_MAX_NOTES]]
        data["mode_tags"] = [_bounded(tag, _MAX_NOTE_LENGTH) for tag in self.mode_tags[:_MAX_NOTES]]
        data["compiled_transition_ids"] = [
            _bounded(value, _MAX_ID_LENGTH)
            for value in self.compiled_transition_ids[:_MAX_TRANSITIONS]
        ]
        data["transition_descriptions"] = [
            _bounded(value, _MAX_NOTE_LENGTH)
            for value in self.transition_descriptions[:_MAX_TRANSITIONS]
        ]
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
