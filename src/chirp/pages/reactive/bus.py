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
    """

    __slots__ = ("_lock", "_subscribers")

    def __init__(self) -> None:
        # scope -> set of subscriber queues
        self._subscribers: dict[str, set[asyncio.Queue[ChangeEvent | None]]] = {}
        self._lock = threading.Lock()

    def emit_sync(self, event: ChangeEvent) -> None:
        """Broadcast a change event synchronously (from any thread).

        Uses ``put_nowait`` so it never blocks.  Drops the event for
        a subscriber if its queue is full (back-pressure).
        """
        with self._lock:
            queues = set(self._subscribers.get(event.scope, set()))
        for queue in queues:
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(event)

    async def emit(self, event: ChangeEvent) -> None:
        """Broadcast a change event (async version)."""
        self.emit_sync(event)

    async def subscribe(self, scope: str) -> AsyncIterator[ChangeEvent]:
        """Subscribe to change events for a specific scope.

        Yields ``ChangeEvent`` objects as they are emitted.  The
        subscription is automatically cleaned up when the iterator
        exits (client disconnects).
        """
        queue: asyncio.Queue[ChangeEvent | None] = asyncio.Queue(maxsize=256)
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
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(None)
