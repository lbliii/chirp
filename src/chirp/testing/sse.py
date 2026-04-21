"""SSE testing utilities.

Provides structured parsing of Server-Sent Events responses
for use in test assertions.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import TYPE_CHECKING

from chirp.realtime.events import SSEEvent

if TYPE_CHECKING:
    from chirp.testing.client import TestClient


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
            events.append(
                SSEEvent(
                    data="\n".join(data_lines),
                    event=event_type,
                    id=event_id,
                    retry=retry,
                )
            )

    return events, heartbeats


class _SseAttrExtractor(HTMLParser):
    """Collect htmx-sse wiring attributes from rendered HTML."""

    def __init__(self) -> None:
        super().__init__()
        self.sse_connects: list[str] = []
        self.sse_swaps: set[str] = set()

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        for name, value in attrs:
            if name == "sse-connect" and value:
                self.sse_connects.append(value)
            elif name == "sse-swap" and value:
                for part in value.split(","):
                    stripped = part.strip()
                    if stripped:
                        self.sse_swaps.add(stripped)


def extract_sse_attrs(html: str) -> tuple[list[str], set[str]]:
    """Return ``(sse-connect values, sse-swap event names)`` from rendered HTML.

    Used by :func:`assert_sse_wired` to cross-check wiring against the
    actual event names a stream emits.
    """
    parser = _SseAttrExtractor()
    parser.feed(html)
    return parser.sse_connects, parser.sse_swaps


async def assert_sse_wired(
    client: TestClient,
    page_path: str,
    sse_path: str,
    *,
    max_events: int = 5,
) -> None:
    """Cross-check SSE wiring between the page and the stream.

    Fails if the page has ``sse-connect`` but no ``sse-swap``, or if a
    listener in the page waits for an event name the stream never emits
    (the class of silent failure you would otherwise only catch in a
    browser).

    Stream-emitted events that no listener consumes are allowed — streams
    may emit ``status``/``close`` metadata that is not a swap target.
    """
    page = await client.get(page_path)
    connects, swaps = extract_sse_attrs(page.text)
    assert connects, (
        f"Page {page_path!r} has no sse-connect attribute; "
        "cannot verify SSE wiring."
    )
    assert swaps, (
        f"Page {page_path!r} has sse-connect={connects!r} but no sse-swap= "
        "attribute. htmx-sse will not wire up any listener without it."
    )
    result = await client.sse(sse_path, max_events=max_events)
    emitted = {evt.event or "message" for evt in result.events}
    dead_listeners = swaps - emitted
    assert not dead_listeners, (
        f"Page listens for sse-swap={sorted(dead_listeners)} but stream "
        f"{sse_path!r} never emits those events (emitted: {sorted(emitted)})."
    )
