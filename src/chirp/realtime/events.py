"""EventStream and SSEEvent types.

Frozen dataclasses for Server-Sent Events. The SSE handler inspects
these to format the wire protocol.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class SSEEvent:
    """A single Server-Sent Event."""

    data: str
    event: str | None = None
    id: str | None = None
    retry: int | None = None

    def encode(self) -> str:
        """Serialize to SSE wire format."""
        lines: list[str] = []
        if self.event:
            lines.append(f"event: {self.event}")
        if self.id:
            lines.append(f"id: {self.id}")
        if self.retry is not None:
            lines.append(f"retry: {self.retry}")
        lines.extend(f"data: {line}" for line in self.data.split("\n"))
        lines.append("")  # Trailing newline to terminate the event
        return "\n".join(lines) + "\n"


@dataclass(frozen=True, slots=True)
class EventStream:
    """Stream Server-Sent Events to the client.

    The generator yields values converted to SSE events:

    - ``str``: sent as data
    - ``dict``: JSON-serialized as data
    - ``Fragment``: rendered via kida, sent on the htmx ``message`` channel
      unless the fragment has a target
    - ``SSEEvent``: sent as-is

    Usage::

        async def stream():
            async for event in bus.subscribe():
                yield Fragment("components/item.html", item=event)
        return EventStream(stream())
    """

    generator: AsyncIterator[Any]
    event_type: str | None = None
    heartbeat_interval: float = 15.0

    def __post_init__(self) -> None:
        if self.heartbeat_interval < 1.0:
            msg = (
                f"EventStream heartbeat_interval={self.heartbeat_interval}s is too low "
                f"(minimum 1.0s). Very short intervals waste bandwidth without "
                f"improving disconnect detection."
            )
            raise ValueError(msg)
        if self.heartbeat_interval > 300.0:
            msg = (
                f"EventStream heartbeat_interval={self.heartbeat_interval}s is too high "
                f"(maximum 300s). Long intervals risk proxy/firewall timeouts "
                f"closing the connection before a heartbeat is sent."
            )
            raise ValueError(msg)
