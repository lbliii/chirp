"""Tool call event bus — async broadcast for real-time dashboards.

When an MCP tool is invoked, a ``ToolCallEvent`` is emitted through the
``ToolEventBus``. SSE routes subscribe to receive events as they happen,
enabling live agent-activity dashboards.

Free-threading safety:
    - ToolCallEvent is a frozen dataclass (immutable, safe to share)
    - ToolEventBus uses a Lock to protect the subscriber set
    - Each subscriber gets its own asyncio.Queue (no shared mutable state)
"""

import asyncio
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
        self._subscribers: set[asyncio.Queue[ToolCallEvent | None]] = set()
        self._lock = threading.Lock()

    async def emit(self, event: ToolCallEvent) -> None:
        """Broadcast an event to all active subscribers."""
        with self._lock:
            subscribers = set(self._subscribers)
        for queue in subscribers:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # Drop event for slow consumers rather than blocking
                pass

    async def subscribe(self) -> AsyncIterator[ToolCallEvent]:
        """Subscribe to tool call events.

        Returns an async iterator that yields events as they are emitted.
        The subscription is automatically cleaned up when the iterator exits.
        """
        queue: asyncio.Queue[ToolCallEvent | None] = asyncio.Queue(maxsize=256)
        with self._lock:
            self._subscribers.add(queue)
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield event
        finally:
            with self._lock:
                self._subscribers.discard(queue)

    def close(self) -> None:
        """Signal all subscribers to stop.

        Puts ``None`` into every queue, which causes the async iterator
        to break cleanly.
        """
        with self._lock:
            for queue in self._subscribers:
                try:
                    queue.put_nowait(None)
                except asyncio.QueueFull:
                    pass
            self._subscribers.clear()
