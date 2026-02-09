"""SSE testing utilities.

Provides structured parsing of Server-Sent Events responses
for use in test assertions.
"""

import contextlib
from dataclasses import dataclass, field

from chirp.realtime.events import SSEEvent


@dataclass(frozen=True, slots=True)
class SSETestResult:
    """Collected events from an SSE endpoint.

    Returned by ``TestClient.sse()`` after the connection closes.
    """

    events: tuple[SSEEvent, ...]
    heartbeats: int
    status: int
    headers: dict[str, str] = field(default_factory=dict)


def parse_sse_frames(raw: str) -> tuple[list[SSEEvent], int]:
    """Parse raw SSE text into structured events and heartbeat count.

    Splits on double-newline boundaries. Each block is parsed into an
    ``SSEEvent``. Comment lines (starting with ``:``) are counted as
    heartbeats if they contain "heartbeat".
    """
    events: list[SSEEvent] = []
    heartbeats = 0

    # SSE frames are separated by blank lines (\n\n)
    blocks = raw.split("\n\n")

    for block in blocks:
        if not block.strip():
            continue

        # Check for heartbeat comments
        if block.startswith(":"):
            if "heartbeat" in block:
                heartbeats += 1
            continue

        # Parse SSE fields
        event_type: str | None = None
        data_lines: list[str] = []
        event_id: str | None = None
        retry: int | None = None

        for line in block.split("\n"):
            if line.startswith("event: "):
                event_type = line[7:]
            elif line.startswith("data: "):
                data_lines.append(line[6:])
            elif line.startswith("id: "):
                event_id = line[4:]
            elif line.startswith("retry: "):
                with contextlib.suppress(ValueError):
                    retry = int(line[7:])
            elif line.startswith(":") and "heartbeat" in line:
                heartbeats += 1

        if data_lines:
            events.append(SSEEvent(
                data="\n".join(data_lines),
                event=event_type,
                id=event_id,
                retry=retry,
            ))

    return events, heartbeats
