"""Reactive event bus for change event broadcasting."""


import asyncio
import contextlib
import logging
import threading
import time
from collections.abc import AsyncIterator, Callable
from typing import Any

from chirp.pages.reactive.events import ChangeEvent, ConnectionInfo

logger = logging.getLogger("chirp.reactive")

# Internal subscriber record: queue + optional connection info
_Sub = tuple[asyncio.Queue[ChangeEvent | None], ConnectionInfo | None]

#: Type for the on_drop callback: (scope, event) -> None
OnDropCallback = Callable[[str, ChangeEvent], Any]

# Throttle window for drop warnings (seconds)
_DROP_LOG_INTERVAL = 10.0


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
        on_drop: Optional callback invoked when an event is dropped
            due to a full subscriber queue.  Receives ``(scope, event)``.
            Called outside the bus lock but still on the emit path —
            keep it fast and non-blocking.
    """

    __slots__ = (
        "_drop_log_counts",
        "_drop_log_last",
        "_dropped_count",
        "_emitted_count",
        "_lock",
        "_maxsize",
        "_on_drop",
        "_subscribers",
    )

    def __init__(
        self,
        *,
        maxsize: int = 256,
        on_drop: OnDropCallback | None = None,
    ) -> None:
        if maxsize < 1:
            msg = f"maxsize must be >= 1, got {maxsize}"
            raise ValueError(msg)
        # scope -> set of (queue, connection_info) tuples
        self._subscribers: dict[str, set[_Sub]] = {}
        self._lock = threading.Lock()
        self._maxsize = maxsize
        self._emitted_count = 0
        self._dropped_count = 0
        self._on_drop = on_drop
        # Throttle state: scope -> (last_log_time, drops_since_last_log)
        self._drop_log_last: dict[str, float] = {}
        self._drop_log_counts: dict[str, int] = {}

    def emit_sync(self, event: ChangeEvent) -> None:
        """Broadcast a change event synchronously (from any thread).

        Uses ``put_nowait`` so it never blocks.  Drops the event for
        a subscriber if its queue is full (back-pressure).  Dropped
        events are logged at WARNING level (throttled per scope).

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
                    self._log_drop(event)
                if self._on_drop is not None:
                    try:
                        self._on_drop(event.scope, event)
                    except Exception:
                        logger.exception("on_drop callback failed for scope=%s", event.scope)

    def _log_drop(self, event: ChangeEvent) -> None:
        """Log a dropped event, throttled to once per scope per interval."""
        now = time.monotonic()
        scope = event.scope
        last = self._drop_log_last.get(scope, 0.0)
        self._drop_log_counts[scope] = self._drop_log_counts.get(scope, 0) + 1

        if now - last >= _DROP_LOG_INTERVAL:
            count = self._drop_log_counts[scope]
            logger.warning(
                "ReactiveBus: dropped %d event(s) for scope=%r (subscriber queue full, maxsize=%d)",
                count,
                scope,
                self._maxsize,
            )
            self._drop_log_last[scope] = now
            self._drop_log_counts[scope] = 0

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
                try:
                    on_disconnect(scope, connection)
                except Exception:
                    logging.getLogger("chirp.reactive").exception(
                        "on_disconnect callback failed for scope=%s", scope
                    )

    def close(self, scope: str | None = None) -> None:
        """Signal subscribers to stop.

        If *scope* is given, only close that scope's subscribers.
        Otherwise close all.
        """
        with self._lock:
            if scope is not None:
                subs = self._subscribers.pop(scope, set())
                # Clean up throttle state for the closed scope
                self._drop_log_last.pop(scope, None)
                self._drop_log_counts.pop(scope, None)
            else:
                subs = set()
                for s in list(self._subscribers):
                    subs |= self._subscribers.pop(s)
                self._drop_log_last.clear()
                self._drop_log_counts.clear()
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
