"""Tool call event bus — async broadcast for real-time dashboards.

When an MCP tool is invoked, a ``ToolCallEvent`` is emitted through the
``ToolEventBus``. SSE routes subscribe to receive events as they happen,
enabling live agent-activity dashboards.

Free-threading safety:
    - ToolCallEvent is a frozen dataclass (immutable, safe to share)
    - ToolEventBus uses a Lock to protect the subscriber set
    - Each subscriber gets its own asyncio.Queue on its owning event loop
    - Cross-thread emitters schedule queue mutation with call_soon_threadsafe
"""

import asyncio
import contextlib
import threading
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ToolCallEvent:
    """A single tool invocation event.

    Emitted by the ``ToolRegistry`` after each successful tool call.
    Consumed by SSE routes for real-time agent dashboards.
    """

    tool_name: str
    arguments: dict[str, Any]
    result: Any
    timestamp: float
    call_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])


_Sub = tuple[asyncio.Queue[ToolCallEvent | None], asyncio.AbstractEventLoop]


class ToolEventBus:
    """Async broadcast channel for tool call events.

    Each call to ``subscribe()`` returns an async iterator backed by its
    own ``asyncio.Queue``. When ``emit()`` is called, the event is placed
    into every active subscriber's queue.

    Usage in SSE routes::

        async def stream():
            async for event in app.tool_events.subscribe():
                yield Fragment("dashboard.html", "row", event=event)
        return EventStream(stream())
    """

    __slots__ = ("_lock", "_subscribers")

    def __init__(self) -> None:
        self._subscribers: set[_Sub] = set()
        self._lock = threading.Lock()

    async def emit(self, event: ToolCallEvent) -> None:
        """Broadcast an event to all active subscribers."""
        with self._lock:
            subscribers = set(self._subscribers)
        for queue, loop in subscribers:
            self._schedule_event(loop, queue, event)

    def _schedule_event(
        self,
        loop: asyncio.AbstractEventLoop,
        queue: asyncio.Queue[ToolCallEvent | None],
        event: ToolCallEvent,
    ) -> None:
        """Enqueue *event* on the queue's owning loop."""
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None
        if running_loop is loop:
            self._deliver_event(queue, event)
            return
        with contextlib.suppress(RuntimeError):
            loop.call_soon_threadsafe(self._deliver_event, queue, event)

    def _deliver_event(
        self,
        queue: asyncio.Queue[ToolCallEvent | None],
        event: ToolCallEvent,
    ) -> None:
        with contextlib.suppress(asyncio.QueueFull):
            queue.put_nowait(event)

    async def subscribe(self) -> AsyncIterator[ToolCallEvent]:
        """Subscribe to tool call events.

        Returns an async iterator that yields events as they are emitted.
        The subscription is automatically cleaned up when the iterator exits.
        """
        queue: asyncio.Queue[ToolCallEvent | None] = asyncio.Queue(maxsize=256)
        loop = asyncio.get_running_loop()
        sub: _Sub = (queue, loop)
        with self._lock:
            self._subscribers.add(sub)
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield event
        finally:
            with self._lock:
                self._subscribers.discard(sub)

    def close(self) -> None:
        """Signal all subscribers to stop.

        Puts ``None`` into every queue, which causes the async iterator
        to break cleanly.
        """
        with self._lock:
            subscribers = set(self._subscribers)
            self._subscribers.clear()
        for queue, loop in subscribers:
            self._schedule_close(loop, queue)

    def _schedule_close(
        self,
        loop: asyncio.AbstractEventLoop,
        queue: asyncio.Queue[ToolCallEvent | None],
    ) -> None:
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None
        if running_loop is loop:
            self._deliver_close(queue)
            return
        with contextlib.suppress(RuntimeError):
            loop.call_soon_threadsafe(self._deliver_close, queue)

    def _deliver_close(self, queue: asyncio.Queue[ToolCallEvent | None]) -> None:
        # Drain one event if needed to guarantee the sentinel lands.
        try:
            queue.put_nowait(None)
        except asyncio.QueueFull:
            with contextlib.suppress(asyncio.QueueEmpty):
                queue.get_nowait()
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(None)
