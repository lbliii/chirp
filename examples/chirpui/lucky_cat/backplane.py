"""DOMAIN — signal fan-out boundary for Lucky Cat.

The ``SignalBackplane`` protocol and the shipped ``InProcessBackplane``
implementation: a transport-agnostic seam between mutation routes in ``app.py``
and the framework's ``app.emit`` fan-out over ``/_chirp/live``. Routes call
``get_backplane().publish(name, value)`` instead of ``app.emit`` directly so a
production deploy can swap in a shared bus without rewriting handlers.

The default ``InProcessBackplane`` delegates to the bound ``App.emit`` — the
current single-worker behavior (``workers=1`` in ``app.py``). A ``RedisBackplane``
skeleton is stubbed for the multi-worker path described in the live-SSE-topics RFC
§12; wire it when ``workers>1`` and pair it with a shared ``AccountStore`` /
external state store (the backplane carries notifications, not source-of-truth).

Pure stdlib for the in-process path; ``RedisBackplane`` would reuse
``chirp[redis]`` when implemented.
"""

import os
import threading
from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class SignalBackplane(Protocol):
    """Transport-agnostic signal fan-out boundary.

    ``publish`` pushes a new value for ``name`` to every ``signal(name)``
    binding. The in-process impl calls ``App.emit``; a Redis impl would
    ``PUBLISH`` to a shared channel so every worker's SSE connection wakes.
    """

    def publish(self, name: str, value: Any) -> None:
        """Fan ``value`` out to every binding of signal ``name``."""
        ...


class InProcessBackplane:
    """Single-process backplane — wraps ``App.emit`` (default)."""

    def __init__(self, emit: Callable[[str, Any], None]) -> None:
        self._emit = emit

    def publish(self, name: str, value: Any) -> None:
        self._emit(name, value)


class RedisBackplane:
    """Stub for multi-worker signal fan-out over Redis pub/sub.

    NOT wired — Lucky Cat pins ``workers=1`` until a shared state store and this
    backplane are both configured. To enable for ``workers>1``:

    1. Set ``LUCKY_CAT_BACKPLANE=redis`` and provide ``REDIS_URL``.
    2. Subscribe each worker's merge stream to ``signal:<name>`` channels and
       call ``App.emit`` on receive (rendered values cross the wire per RFC §12).
    3. Pair with a shared ``AccountStore`` — the backplane is fan-out transport,
       not a ledger; wallet balance must live in Redis/Postgres too.

    Reuses the ``chirp[redis]`` extra when implemented.
    """

    def __init__(self, *, redis_url: str, emit: Callable[[str, Any], None]) -> None:
        self._redis_url = redis_url
        self._emit = emit
        # self._client = redis.from_url(redis_url)
        # self._pubsub = self._client.pubsub()
        # wire subscribe loop -> self._emit(name, value) on each worker

    def publish(self, name: str, value: Any) -> None:
        """Publish to Redis AND the local bus (leader/worker topology TBD)."""
        raise NotImplementedError(
            "RedisBackplane is a skeleton only — set LUCKY_CAT_BACKPLANE=memory "
            "(default) or implement subscribe wiring for workers>1"
        )


# ---------------------------------------------------------------------------
# Backplane selector — LUCKY_CAT_BACKPLANE (default "memory"). Cached singleton.
# ---------------------------------------------------------------------------

_backplane_lock = threading.Lock()
_backplane: SignalBackplane | None = None
_emit_fn: Callable[[str, Any], None] | None = None


def bind_emit(emit: Callable[[str, Any], None]) -> None:
    """Bind ``App.emit`` once at startup — must run before the first ``publish``."""
    global _emit_fn, _backplane
    with _backplane_lock:
        _emit_fn = emit
        _backplane = None


def _build_backplane(emit: Callable[[str, Any], None]) -> SignalBackplane:
    source = os.environ.get("LUCKY_CAT_BACKPLANE", "memory").strip().lower()
    if source == "redis":
        redis_url = os.environ.get("REDIS_URL", "").strip()
        if not redis_url:
            import logging

            logging.getLogger("lucky_cat.backplane").warning(
                "LUCKY_CAT_BACKPLANE=redis but REDIS_URL is unset; "
                "falling back to InProcessBackplane."
            )
            return InProcessBackplane(emit)
        return RedisBackplane(redis_url=redis_url, emit=emit)
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
