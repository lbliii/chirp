"""DOMAIN — Lucky Cat's mutation-to-signal publication seam.

Both adapters delegate to ``App.emit``. Chirp itself selects process-local memory
or its private Redis data plane from ``AppConfig.redis_url``; this example seam
keeps route code transport-agnostic while external state remains app-owned.
"""

import os
import threading
from typing import Any, Protocol, runtime_checkable


class _EmitFn(Protocol):
    def __call__(self, name: str, value: Any, *, audience_key: str = "") -> None: ...


@runtime_checkable
class SignalBackplane(Protocol):
    """Transport-agnostic signal fan-out boundary.

    ``publish`` pushes a new value for ``name`` to every ``signal(name)``
    binding. Both example adapters call ``App.emit``; Chirp owns transport.
    """

    def publish(self, name: str, value: Any, *, audience_key: str = "") -> None:
        """Fan ``value`` out to every binding of signal ``name``."""
        ...


class InProcessBackplane:
    """Single-process backplane — wraps ``App.emit`` (default)."""

    def __init__(self, emit: _EmitFn) -> None:
        self._emit = emit

    def publish(self, name: str, value: Any, *, audience_key: str = "") -> None:
        self._emit(name, value, audience_key=audience_key)


class RedisBackplane:
    """Example label for ``App.emit`` when Chirp's private Redis plane is selected."""

    def __init__(self, *, emit: _EmitFn) -> None:
        self._emit = emit

    def publish(self, name: str, value: Any, *, audience_key: str = "") -> None:
        """Delegate to Chirp, which renders and publishes through private Redis."""
        self._emit(name, value, audience_key=audience_key)


# ---------------------------------------------------------------------------
# Backplane selector — LUCKY_CAT_BACKPLANE (default "memory"). Cached singleton.
# ---------------------------------------------------------------------------

_backplane_lock = threading.Lock()
_backplane: SignalBackplane | None = None
_emit_fn: _EmitFn | None = None


def bind_emit(emit: _EmitFn) -> None:
    """Bind ``App.emit`` once at startup — must run before the first ``publish``."""
    global _emit_fn, _backplane
    with _backplane_lock:
        _emit_fn = emit
        _backplane = None


def _build_backplane(emit: _EmitFn) -> SignalBackplane:
    source = os.environ.get("LUCKY_CAT_BACKPLANE", "memory").strip().lower()
    if source == "redis":
        redis_url = os.environ.get("CHIRP_REDIS_URL", "").strip()
        if not redis_url:
            import logging

            logging.getLogger("lucky_cat.backplane").warning(
                "LUCKY_CAT_BACKPLANE=redis but CHIRP_REDIS_URL is unset; "
                "falling back to InProcessBackplane."
            )
            return InProcessBackplane(emit)
        return RedisBackplane(emit=emit)
    return InProcessBackplane(emit)


def get_backplane() -> SignalBackplane:
    """Return the process-wide backplane selected by ``LUCKY_CAT_BACKPLANE``."""
    global _backplane
    if _backplane is None:
        with _backplane_lock:
            if _backplane is None:
                if _emit_fn is None:
                    msg = "backplane.bind_emit(app.emit) must run before publish"
                    raise RuntimeError(msg)
                _backplane = _build_backplane(_emit_fn)
    return _backplane


def reset() -> None:
    """Drop the cached backplane — used when reloading ``app.py`` in tests."""
    global _backplane
    with _backplane_lock:
        _backplane = None
