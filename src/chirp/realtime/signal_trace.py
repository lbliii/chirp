"""Request-scoped signal emit tracing for DevTools."""

from __future__ import annotations

import base64
import json
from dataclasses import asdict, dataclass
from typing import Any

from chirp.context import request_var
from chirp.http.request import Request

SIGNAL_EMIT_TRACE_KEY = "_chirp_signal_emits"


@dataclass(frozen=True, slots=True)
class SignalEmitRecord:
    """One signal fan-out recorded during a mutation request."""

    name: str
    audience_key: str
    scope: str

    def payload(self) -> dict[str, Any]:
        return asdict(self)


def _current_request() -> Request | None:
    try:
        return request_var.get()
    except LookupError:
        return None


def record_signal_emit(
    name: str, *, audience_key: str = "", request: Request | None = None
) -> None:
    """Append a signal emit to the active request trace, if any."""
    req = request if request is not None else _current_request()
    if req is None:
        return
    scope = "session" if audience_key else "global"
    trace = req._cache.setdefault(SIGNAL_EMIT_TRACE_KEY, [])
    if isinstance(trace, list):
        trace.append(SignalEmitRecord(name=name, audience_key=audience_key, scope=scope))


def get_signal_emit_trace(request: Any) -> tuple[SignalEmitRecord, ...]:
    cache = getattr(request, "_cache", None)
    if not isinstance(cache, dict):
        return ()
    trace = cache.get(SIGNAL_EMIT_TRACE_KEY)
    if not isinstance(trace, list):
        return ()
    return tuple(item for item in trace if isinstance(item, SignalEmitRecord))


def encode_signal_emit_trace(records: tuple[SignalEmitRecord, ...]) -> str:
    payload = [record.payload() for record in records]
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return base64.b64encode(raw).decode("ascii")
