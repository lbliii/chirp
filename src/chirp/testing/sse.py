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
        self.htmx4_connects: list[str] = []
        self.htmx4_targets: set[str] = set()
        self.ids: set[str] = set()
        self.signal_names: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {name.lower(): value for name, value in attrs}
        element_id = attr_map.get("id")
        if element_id:
            self.ids.add(element_id)
        signal_name = attr_map.get("data-chirp-signal")
        if signal_name:
            self.signal_names.add(signal_name)
        connect = attr_map.get("hx-sse:connect")
        if connect:
            self.htmx4_connects.append(connect)
            target = attr_map.get("hx-target")
            if target:
                self.htmx4_targets.add(target)
        for name, value in attrs:
            if name == "sse-connect" and value:
                self.sse_connects.append(value)
            elif name == "sse-swap" and value:
                for part in value.split(","):
                    stripped = part.strip()
                    if stripped:
                        self.sse_swaps.add(stripped)


def extract_sse_attrs(html: str) -> tuple[list[str], set[str]]:
    """Return ``(connection URLs, legacy sse-swap event names)`` from HTML.

    Connection URLs include both htmx 2 ``sse-connect`` and htmx 4
    ``hx-sse:connect`` values. The second item remains the legacy named-swap
    set for backward compatibility; htmx 4 uses unnamed HTML and partials.
    """
    parser = _SseAttrExtractor()
    parser.feed(html)
    return [*parser.sse_connects, *parser.htmx4_connects], parser.sse_swaps


class _SsePayloadExtractor(HTMLParser):
    """Collect bounded htmx 4 target metadata from one SSE data payload."""

    def __init__(self) -> None:
        super().__init__()
        self.partial_targets: set[str] = set()
        self.oob_targets: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {name.lower(): value for name, value in attrs}
        if tag.lower() == "hx-partial" and attr_map.get("hx-target"):
            self.partial_targets.add(attr_map["hx-target"] or "")
        if "hx-swap-oob" in attr_map and attr_map.get("id"):
            self.oob_targets.add(attr_map["id"] or "")


async def assert_sse_wired(
    client: TestClient,
    page_path: str,
    sse_path: str,
    *,
    max_events: int = 5,
) -> None:
    """Cross-check version-aware SSE wiring between the page and the stream.

    Htmx 2 checks named ``sse-swap`` listeners against emitted event names.
    Htmx 4 selects the fetch-stream request dialect and checks connection,
    partial, and OOB targets against rendered page IDs.

    Stream-emitted events that no listener consumes are allowed — streams
    may emit ``status``/``close`` metadata that is not a swap target.
    """
    page = await client.get(page_path)
    wiring = _SseAttrExtractor()
    wiring.feed(page.text)
    connects = [*wiring.sse_connects, *wiring.htmx4_connects]
    swaps = wiring.sse_swaps
    assert connects, (
        f"Page {page_path!r} has no sse-connect or hx-sse:connect attribute; "
        "cannot verify SSE wiring."
    )
    if wiring.htmx4_connects:
        assert not wiring.sse_connects, (
            f"Page {page_path!r} mixes htmx 4 hx-sse:connect with legacy sse-connect attributes."
        )
        assert not wiring.sse_swaps, (
            f"Page {page_path!r} mixes htmx 4 hx-sse:connect with legacy sse-swap attributes."
        )
        result = await client.sse(sse_path, request_type="partial", max_events=max_events)
        for target in wiring.htmx4_targets:
            assert target.startswith("#"), (
                f"htmx 4 SSE connection target {target!r} is not an id selector."
            )
            assert target[1:] in wiring.ids, (
                f"htmx 4 SSE connection target {target!r} does not resolve to a rendered page id."
            )
        for event in result.events:
            if event.event is not None:
                continue
            payload = _SsePayloadExtractor()
            payload.feed(event.data)
            for target in payload.partial_targets:
                if target.startswith("#"):
                    assert target[1:] in wiring.ids, (
                        f"htmx 4 SSE partial target {target!r} does not resolve to a rendered page id."
                    )
                    continue
                prefix = '[data-chirp-signal="'
                assert target.startswith(prefix), (
                    f"htmx 4 SSE partial target {target!r} is neither an id nor a signal selector."
                )
                assert target.endswith('"]'), (
                    f"htmx 4 SSE signal target {target!r} is not a bounded attribute selector."
                )
                signal_name = target[len(prefix) : -2]
                assert signal_name in wiring.signal_names, (
                    f"htmx 4 SSE signal target {target!r} has no rendered data-chirp-signal sink."
                )
            for target in payload.oob_targets:
                assert target in wiring.ids, (
                    f"htmx 4 SSE OOB target #{target} does not resolve to a rendered page id."
                )
            if not payload.partial_targets and not payload.oob_targets:
                assert wiring.htmx4_targets, (
                    "htmx 4 SSE emitted unnamed main HTML, but the connection has no explicit "
                    "hx-target. The source element could replace itself and close the stream."
                )
        return
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
