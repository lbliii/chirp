"""Notifications log for Lucky Cat — the thread-safe store behind the topbar bell.

Per-visitor state (#285): each session carries its own bell log via
:mod:`session_store`. Price-move alerts from the live signal source broadcast to
every active session; fills and deposits append only to the mutating session.

Convention: frozen-value records, session-scoped state behind the registry lock,
and ``reset()`` for test isolation.
"""

import time
from dataclasses import dataclass

import session_store
from wallet import INITIAL_MEOW

# Bounded ring — the bell shows the most recent few; older entries fall off the
# store after _MAX_LOG (50) so a long-running process never grows without bound.
# The dropdown renders the newest 12 (``snapshot``/``recent`` default); read
# notifications stay in the list until they age out of the ring — opening the
# bell clears the unread badge, not the history rows.
_MAX_LOG = 50


@dataclass(frozen=True, slots=True)
class Notification:
    """One bell entry — an immutable, append-only event record."""

    id: int
    kind: str
    title: str
    body: str
    ts: float


@dataclass(frozen=True, slots=True)
class NotifFeed:
    """The ``notifications`` signal VALUE — the recent rows AND the unread count."""

    notes: tuple[Notification, ...]
    unread: int


def _slice(state) -> session_store.NotificationSlice:
    notes = state.notifications
    assert notes is not None
    return notes


def _append_locked(
    notes: session_store.NotificationSlice, kind: str, title: str, body: str
) -> Notification:
    note = Notification(
        id=notes.next_id,
        kind=kind,
        title=title,
        body=body,
        ts=time.time(),
    )
    notes.next_id += 1
    notes.log.insert(0, note)
    del notes.log[_MAX_LOG:]
    return note


def add(kind: str, title: str, body: str = "") -> Notification:
    """Append a notification and return it (newest first in the log)."""
    with session_store.locked(balance_seed=INITIAL_MEOW) as state:
        return _append_locked(_slice(state), kind, title, body)


def add_broadcast(kind: str, title: str, body: str = "") -> None:
    """Append the same notification to every active session (price-move alerts)."""
    session_store.broadcast_notifications(lambda notes: _append_locked(notes, kind, title, body))


def recent(limit: int = 12) -> tuple[Notification, ...]:
    """The most recent notifications, newest first."""
    with session_store.locked(balance_seed=INITIAL_MEOW) as state:
        return tuple(_slice(state).log[:limit])


def unread_count() -> int:
    """How many notifications sit above the read watermark."""
    with session_store.locked(balance_seed=INITIAL_MEOW) as state:
        notes = _slice(state)
        return sum(1 for n in notes.log if n.id > notes.read_through_id)


def snapshot(limit: int = 12) -> NotifFeed:
    """The recent rows + unread count, captured atomically."""
    with session_store.locked(balance_seed=INITIAL_MEOW) as state:
        notes = _slice(state)
        rows = tuple(notes.log[:limit])
        unread = sum(1 for n in notes.log if n.id > notes.read_through_id)
    return NotifFeed(notes=rows, unread=unread)


def mark_all_read() -> int:
    """Mark everything currently in the log read; return the new (zero) unread count."""
    with session_store.locked(balance_seed=INITIAL_MEOW) as state:
        notes = _slice(state)
        if notes.log:
            notes.read_through_id = max(notes.read_through_id, notes.log[0].id)
        return 0


def latest_id() -> int:
    """The id of the newest record (0 when empty) — the SSE's drain start point."""
    with session_store.locked(balance_seed=INITIAL_MEOW) as state:
        notes = _slice(state)
        return notes.log[0].id if notes.log else 0


def drain_since(last_id: int) -> tuple[Notification, ...]:
    """Notifications with ``id > last_id``, OLDEST first (drain order)."""
    with session_store.locked(balance_seed=INITIAL_MEOW) as state:
        newer = [n for n in _slice(state).log if n.id > last_id]
    newer.sort(key=lambda n: n.id)
    return tuple(newer)


def reset() -> None:
    """Clear every session bucket — used by the test fixture."""
    session_store.reset()
