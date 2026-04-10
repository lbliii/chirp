"""Reactive event bus for change event broadcasting."""

from __future__ import annotations

import asyncio
import contextlib
import threading
from collections.abc import AsyncIterator

from chirp.pages.reactive.events import ChangeEvent


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
        # scope -> set of subscriber queues
        self._subscribers: dict[str, set[asyncio.Queue[ChangeEvent | None]]] = {}
        self._lock = threading.Lock()
        self._maxsize = maxsize
        self._emitted_count = 0
        self._dropped_count = 0

    def emit_sync(self, event: ChangeEvent) -> None:
        """Broadcast a change event synchronously (from any thread).

        Uses ``put_nowait`` so it never blocks.  Drops the event for
        a subscriber if its queue is full (back-pressure).
        """
        with self._lock:
            queues = set(self._subscribers.get(event.scope, set()))
            self._emitted_count += 1
        for queue in queues:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                with self._lock:
                    self._dropped_count += 1

    async def emit(self, event: ChangeEvent) -> None:
        """Broadcast a change event (async version)."""
        self.emit_sync(event)

    async def subscribe(self, scope: str) -> AsyncIterator[ChangeEvent]:
        """Subscribe to change events for a specific scope.

        Yields ``ChangeEvent`` objects as they are emitted.  The
        subscription is automatically cleaned up when the iterator
        exits (client disconnects).
        """
        queue: asyncio.Queue[ChangeEvent | None] = asyncio.Queue(maxsize=self._maxsize)
        with self._lock:
            self._subscribers.setdefault(scope, set()).add(queue)
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
                    scope_set.discard(queue)
                    if not scope_set:
                        del self._subscribers[scope]

    def close(self, scope: str | None = None) -> None:
        """Signal subscribers to stop.

        If *scope* is given, only close that scope's subscribers.
        Otherwise close all.
        """
        with self._lock:
            if scope is not None:
                queues = self._subscribers.pop(scope, set())
            else:
                queues = set()
                for s in list(self._subscribers):
                    queues |= self._subscribers.pop(s)
        for queue in queues:
            # Drain one event if needed to guarantee the sentinel lands.
            # This ensures close() is reliable even with small maxsize.
            try:
                queue.put_nowait(None)
            except asyncio.QueueFull:
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
                with contextlib.suppress(asyncio.QueueFull):
                    queue.put_nowait(None)

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
