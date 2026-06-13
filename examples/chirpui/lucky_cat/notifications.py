"""Notifications log for Lucky Cat — the thread-safe store behind the topbar bell.

The bell popover shows a short feed of account + market events: an order *fill*,
a *deposit*, and live *price-move* alerts the ``notifications`` SIGNAL raises as
the SimFeed walks (app.py ``notifications_signal``). Like ``wallet.py`` /
``trade_store.py`` it is the example's mutable shared state, so it follows the
same store convention: frozen-value records, a single ``threading.Lock``, and a
``reset()`` for test isolation (wired into ``conftest.py`` alongside
``feed.reset()`` / ``wallet.reset()`` / ``trade_store.reset()``).

Single source of truth: *every* notification — fills, deposits, and the signal's
price-move alerts — is appended through :func:`add`, so the unread badge count
can never drift from the rendered rows. Each record carries a monotonic ``id``;
the live channel is now the ``notifications`` SIGNAL on the single ``/_chirp/live``
connection — it emits a :class:`NotifFeed` :func:`snapshot` (the recent rows AND
the unread count, captured atomically; coalescing-latest) whenever the log
changes, and the derived ``notif_badge`` / ``notif_announce`` signals compute
PURELY from ``feed.unread`` in the same cascade (the pure-derived contract — no
second store read on a different thread/worker). ``mark_all_read`` advances the
read watermark so opening the bell clears the badge.

Free-threading safety (this example's whole point): the log, the id counter, and
the read-watermark all live under one ``_lock``. Concurrent ``add`` calls from
racing route handlers and the signal source worker can interleave without
corrupting the list or double-issuing an id, and ``unread_count`` is always
consistent with ``mark_all_read``.

Pure stdlib only (``threading``, ``time``, ``dataclasses``); importing this
module does not re-enable the GIL on a 3.14t build.
"""

import threading
import time
from dataclasses import dataclass

# Bounded ring — the bell shows the most recent few; older entries fall off so a
# long-running process never grows the log without bound. Newest first.
_MAX_LOG = 50


@dataclass(frozen=True, slots=True)
class Notification:
    """One bell entry — an immutable, append-only event record.

    ``id`` is monotonic (the drain watermark + the OOB row key); ``kind`` is the
    semantic class (``"fill"`` / ``"deposit"`` / ``"price"``) that picks the row
    icon + jade/red accent; ``title`` is the bold lead line and ``body`` the muted
    detail; ``ts`` is the wall-clock epoch of the event.
    """

    id: int
    kind: str
    title: str
    body: str
    ts: float


@dataclass(frozen=True, slots=True)
class NotifFeed:
    """The ``notifications`` signal VALUE — the recent rows AND the unread count.

    The pure-derived contract: a ``@app.derived`` must compute solely from its
    input signal VALUES, never from external/process-local mutable state, or it is
    non-deterministic across workers (each worker holds a separate store). So the
    ``notifications`` signal carries BOTH the rendered ``notes`` and the watermark-
    aware ``unread`` count in ONE immutable snapshot, and the derived
    ``notif_badge`` / ``notif_announce`` read ``feed.unread`` directly — they never
    re-read :func:`unread_count`. :func:`snapshot` captures both fields atomically
    under the one lock, so the count can never disagree with the rows it ships.
    """

    notes: tuple[Notification, ...]
    unread: int


# Module state — all under one lock. ``_read_through_id`` is the highest id the
# user has marked read; ``unread_count`` is how many records sit above it.
_lock = threading.Lock()
_log: list[Notification] = []
_next_id: int = 1
_read_through_id: int = 0


def add(kind: str, title: str, body: str = "") -> Notification:
    """Append a notification and return it (newest first in the log).

    Issues the next monotonic id, prepends the record, and trims the ring to
    ``_MAX_LOG``. A fresh record is unread by construction (its id is above the
    read watermark), so the bell badge bumps without a separate counter.
    """
    global _next_id
    with _lock:
        note = Notification(
            id=_next_id,
            kind=kind,
            title=title,
            body=body,
            ts=time.time(),
        )
        _next_id += 1
        _log.insert(0, note)
        del _log[_MAX_LOG:]
        return note


def recent(limit: int = 12) -> tuple[Notification, ...]:
    """The most recent notifications, newest first (sync, cheap — safe in a
    context provider / page render)."""
    with _lock:
        return tuple(_log[:limit])


def unread_count() -> int:
    """How many notifications sit above the read watermark."""
    with _lock:
        return sum(1 for n in _log if n.id > _read_through_id)


def snapshot(limit: int = 12) -> NotifFeed:
    """The ``notifications`` signal value — the recent rows + unread count, atomic.

    Reads BOTH fields under one lock acquisition so the count can never drift from
    the rows it ships. This is the value emitted to the ``notifications`` signal;
    the derived ``notif_badge`` / ``notif_announce`` compute PURELY from
    ``feed.unread`` (the pure-derived contract — no second store read on a
    different thread/worker).
    """
    with _lock:
        notes = tuple(_log[:limit])
        unread = sum(1 for n in _log if n.id > _read_through_id)
    return NotifFeed(notes=notes, unread=unread)


def mark_all_read() -> int:
    """Mark everything currently in the log read; return the new (zero) unread
    count. Opening the bell calls this — the watermark advances to the newest id
    so the badge clears, and later arrivals (above the new watermark) re-light it.
    """
    global _read_through_id
    with _lock:
        if _log:
            _read_through_id = max(_read_through_id, _log[0].id)
        return 0


def latest_id() -> int:
    """The id of the newest record (0 when empty) — the SSE's drain start point."""
    with _lock:
        return _log[0].id if _log else 0


def drain_since(last_id: int) -> tuple[Notification, ...]:
    """Notifications with ``id > last_id``, OLDEST first (drain order).

    The SSE loop holds the highest id it has already streamed and calls this each
    tick; the oldest-first order lets it prepend rows in arrival order so the
    newest ends up on top. Returns an empty tuple when nothing is new.
    """
    with _lock:
        newer = [n for n in _log if n.id > last_id]
    newer.sort(key=lambda n: n.id)
    return tuple(newer)


def reset() -> None:
    """Clear the log + counters to the empty seed — used by the test fixture."""
    global _next_id, _read_through_id
    with _lock:
        _log.clear()
        _next_id = 1
        _read_through_id = 0
