"""App-level signal emit bridge for negotiation and handlers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from chirp.realtime.signal_globals import current_signal_audience

_emit_impl: Callable[..., None] | None = None


def register_emit_impl(fn: Callable[..., None]) -> None:
    """Register the app's ``emit`` implementation (called once at freeze)."""
    global _emit_impl
    _emit_impl = fn


def emit_signal(name: str, value: Any, *, audience_key: str | None = None) -> None:
    """Emit a signal during request handling using the registered app emitter."""
    if _emit_impl is None:
        msg = (
            "No signal emitter registered; declare @app.signal handlers and "
            "freeze the app before emitting"
        )
        raise RuntimeError(msg)
    aud = current_signal_audience() if audience_key is None else audience_key
    _emit_impl(name, value, audience_key=aud)


def clear_emit_impl() -> None:
    """Reset the bridge (tests)."""
    global _emit_impl
    _emit_impl = None
