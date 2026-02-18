"""Security audit events.

Small opt-in event channel for authentication and authorization telemetry.
Applications can register a sink to forward events to logs, metrics, or SIEM.
"""

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from time import time
from typing import Any


@dataclass(frozen=True, slots=True)
class SecurityEvent:
    """A structured security event."""

    name: str
    timestamp: float = field(default_factory=time)
    path: str | None = None
    method: str | None = None
    user_id: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


type SecurityEventSink = Callable[[SecurityEvent], None]


_sink_lock = threading.Lock()
_sink: SecurityEventSink | None = None


def set_security_event_sink(sink: SecurityEventSink | None) -> None:
    """Set a process-wide sink for security events.

    Pass ``None`` to disable event delivery.
    """
    global _sink
    with _sink_lock:
        _sink = sink


def emit_security_event(
    name: str,
    *,
    request: Any | None = None,
    user_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Emit a best-effort security event to the configured sink."""
    with _sink_lock:
        sink = _sink
    if sink is None:
        return

    path = None
    method = None
    if request is not None:
        path = getattr(request, "path", None)
        method = getattr(request, "method", None)

    event = SecurityEvent(
        name=name,
        path=path,
        method=method,
        user_id=user_id,
        details=details or {},
    )
    sink(event)
