"""Reactive event bus for change event broadcasting."""

from __future__ import annotations

import asyncio
import contextlib
import threading
from collections.abc import AsyncIterator, Callable

from chirp.pages.reactive.events import ChangeEvent, ConnectionInfo

# Internal subscriber record: queue + optional connection info
_Sub = tuple[asyncio.Queue[ChangeEvent | None], ConnectionInfo | None]


class ReactiveBus:
    """Broadcast channel for data change events.

    Thread-safe.  Each call to ``subscribe(scope)`` returns an async
    iterator that yields ``ChangeEvent``s for that scope.  When
    ``emit()`` is called, the event is placed into every matching
    subscriber's queue.

    Modeled on chirp's ``ToolEventBus`` but scoped per-key.

    Args:
        maxsize: Maximum queue depth per subscriber.  Events are
            silently dropped when a subscriber's queue is full
            (back-pressure).  Default: 256.
    """

    __slots__ = ("_dropped_count", "_emitted_count", "_lock", "_maxsize", "_subscribers")

    def __init__(self, *, maxsize: int = 256) -> None:
        if maxsize < 1:
            msg = f"maxsize must be >= 1, got {maxsize}"
            raise ValueError(msg)
        # scope -> set of (queue, connection_info) tuples
        self._subscribers: dict[str, set[_Sub]] = {}
        self._lock = threading.Lock()
        self._maxsize = maxsize
        self._emitted_count = 0
        self._dropped_count = 0

    def emit_sync(self, event: ChangeEvent) -> None:
        """Broadcast a change event synchronously (from any thread).

        Uses ``put_nowait`` so it never blocks.  Drops the event for
        a subscriber if its queue is full (back-pressure).

        If ``event.audience`` is set, only delivers to subscribers
        whose ``ConnectionInfo.user_id`` is in the audience set.
        Subscribers without ``ConnectionInfo`` are skipped when
        audience filtering is active.
        """
        with self._lock:
            subs = set(self._subscribers.get(event.scope, set()))
            self._emitted_count += 1
        for queue, conn in subs:
            # Audience filtering: skip subscribers not in the audience
            if event.audience is not None and (conn is None or conn.user_id not in event.audience):
                continue
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                with self._lock:
                    self._dropped_count += 1

    async def emit(self, event: ChangeEvent) -> None:
        """Broadcast a change event (async version)."""
        self.emit_sync(event)

    async def subscribe(
        self,
        scope: str,
        *,
        connection: ConnectionInfo | None = None,
        on_disconnect: Callable[[str, ConnectionInfo | None], None] | None = None,
    ) -> AsyncIterator[ChangeEvent]:
        """Subscribe to change events for a specific scope.

        Yields ``ChangeEvent`` objects as they are emitted.  The
        subscription is automatically cleaned up when the iterator
        exits (client disconnects).

        Args:
            scope: Scope key to subscribe to.
            connection: Optional identity for this subscriber.  Enables
                audience filtering and presence tracking.
            on_disconnect: Optional callback invoked when this subscriber
                exits (normal or exception).  Receives ``(scope, connection)``.
        """
        queue: asyncio.Queue[ChangeEvent | None] = asyncio.Queue(maxsize=self._maxsize)
        sub: _Sub = (queue, connection)
        with self._lock:
            self._subscribers.setdefault(scope, set()).add(sub)
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield event
        finally:
            with self._lock:
                scope_set = self._subscribers.get(scope)
                if scope_set is not None:
                    scope_set.discard(sub)
                    if not scope_set:
                        del self._subscribers[scope]
            if on_disconnect is not None:
                on_disconnect(scope, connection)

    def close(self, scope: str | None = None) -> None:
        """Signal subscribers to stop.

        If *scope* is given, only close that scope's subscribers.
        Otherwise close all.
        """
        with self._lock:
            if scope is not None:
                subs = self._subscribers.pop(scope, set())
            else:
                subs = set()
                for s in list(self._subscribers):
                    subs |= self._subscribers.pop(s)
        for queue, _conn in subs:
            # Drain one event if needed to guarantee the sentinel lands.
            # This ensures close() is reliable even with small maxsize.
            try:
                queue.put_nowait(None)
            except asyncio.QueueFull:
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
                with contextlib.suppress(asyncio.QueueFull):
                    queue.put_nowait(None)

    # -- Presence --

    def presence(self, scope: str) -> frozenset[ConnectionInfo]:
        """Return all active connections for a scope.

        Only includes subscribers that provided a ``ConnectionInfo``
        at subscribe time.
        """
        with self._lock:
            subs = self._subscribers.get(scope, set())
            return frozenset(conn for _, conn in subs if conn is not None)

    # -- Observability --

    @property
    def emitted_count(self) -> int:
        """Total number of events emitted (including dropped)."""
        with self._lock:
            return self._emitted_count

    @property
    def dropped_count(self) -> int:
        """Total number of events dropped due to full subscriber queues."""
        with self._lock:
            return self._dropped_count

    @property
    def subscriber_count(self) -> int:
        """Total number of active subscribers across all scopes."""
        with self._lock:
            return sum(len(s) for s in self._subscribers.values())
