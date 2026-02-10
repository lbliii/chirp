---
title: Server-Sent Events
description: Push real-time HTML updates to the browser
draft: false
weight: 20
lang: en
type: doc
tags: [sse, real-time, events, htmx]
keywords: [sse, server-sent-events, eventstream, real-time, push, htmx]
category: guide
---

## What Are SSE?

Server-Sent Events (SSE) are a standard browser API for receiving a stream of events from the server over a persistent HTTP connection. Unlike WebSockets, SSE is:

- **One-directional** -- server pushes to client
- **Plain HTTP** -- no protocol upgrade, no special infrastructure
- **Auto-reconnecting** -- the browser reconnects automatically
- **Text-based** -- simple `text/event-stream` format

## EventStream

Return an `EventStream` from a route handler to start pushing events:

```python
from chirp import EventStream

@app.route("/events")
async def events():
    async def stream():
        while True:
            data = await get_next_update()
            yield data
    return EventStream(stream())
```

The generator yields values. Chirp formats them as SSE wire protocol and sends them to the client.

## Yield Types

The generator can yield different types:

```python
async def stream():
    # String -- sent as SSE data field
    yield "Hello, World!"

    # Dict -- JSON-serialized as SSE data
    yield {"count": 42, "status": "ok"}

    # Fragment -- rendered via kida, sent as named SSE event
    # target= becomes the SSE event name (default: "fragment")
    yield Fragment("components/notification.html", "alert",
                   target="notification", message="New alert")

    # SSEEvent -- full control over event type, id, retry
    yield SSEEvent(data="custom", event="ping", id="1")
```

## SSEEvent

For fine-grained control, yield `SSEEvent` objects:

```python
from chirp import SSEEvent

async def stream():
    yield SSEEvent(
        data="User joined",
        event="user-join",     # Event type (client filters on this)
        id="evt-42",           # Last-Event-ID for reconnection
        retry=5000,            # Reconnection interval in ms
    )
```

## Real-Time HTML with htmx

The killer pattern: combine SSE with htmx to push rendered HTML fragments in real-time.

Server:

```python
@app.route("/notifications")
async def notifications():
    async def stream():
        async for event in notification_bus.subscribe():
            yield Fragment("components/notification.html", "alert",
                target="notification",
                message=event.message,
                time=event.timestamp,
            )
    return EventStream(stream())
```

Client (using htmx SSE extension):

```html
<div hx-ext="sse" sse-connect="/notifications">
  <div sse-swap="notification" hx-swap="beforeend">
    <!-- Fragments are swapped in here -->
  </div>
</div>
```

> **Important**: `sse-swap` must be on a **child** of the `sse-connect` element, not the same element. htmx uses `querySelectorAll` internally, which does not include the root element itself.

The server renders HTML, the browser swaps it in. Zero client-side JavaScript for the rendering logic.

## Live Dashboard Example

A more complete example -- a dashboard that streams stats updates:

```python
@app.route("/dashboard/live")
async def live_stats():
    async def stream():
        while True:
            stats = await get_current_stats()
            # Fragment.target becomes the SSE event name.
            # No need to wrap in SSEEvent -- chirp handles it.
            yield Fragment("dashboard.html", "stats_panel",
                           target="stats-update", stats=stats)
            await asyncio.sleep(5)
    return EventStream(stream())
```

```html
<section hx-ext="sse"
         sse-connect="/dashboard/live"
         hx-disinherit="hx-target hx-swap">
  <div id="stats" sse-swap="stats-update">
    {# Initial stats rendered server-side #}
    {% block stats_panel %}
      ...
    {% endblock %}
  </div>
</section>
```

> **Tip**: Add `hx-disinherit="hx-target hx-swap"` on the `sse-connect` element to prevent layout-level `hx-target` from bleeding into SSE swap targets. Without this, SSE fragments can accidentally replace the wrong region.

## Error Boundaries

Chirp isolates rendering failures per-event so one bad block doesn't crash the entire stream.

If a `Fragment` fails to render:

- **Production** (`debug=False`): the event is silently skipped, the stream continues
- **Debug** (`debug=True`): an error event targets the specific block, replacing it with inline error HTML

```html
<!-- In debug mode, a failed "presence" block becomes: -->
<div class="chirp-block-error" data-block="presence_list">
  <strong>UndefinedError</strong>: &#x27;users&#x27; is undefined
</div>
```

All other blocks on the page keep updating normally. The next change event that touches the broken block will attempt to re-render it -- natural recovery without retries.

For reactive streams, if the `context_builder()` function itself raises (e.g., a deleted record), the entire event is skipped and the stream waits for the next change. See [[docs/reference/errors|Error Reference]] for the full error hierarchy.

## Connection Lifecycle

Chirp manages the SSE connection lifecycle automatically:

1. **Event producer** -- consumes the generator, formats events, sends as ASGI body chunks
2. **Disconnect monitor** -- watches for `http.disconnect`, cancels the producer
3. **Heartbeat** -- sends `: heartbeat` comments on idle to keep the connection alive

## Testing SSE

Use the `TestClient.sse()` method:

```python
from chirp.testing import TestClient

async def test_notifications():
    async with TestClient(app) as client:
        result = await client.sse("/notifications", max_events=3)
        assert len(result.events) == 3
        assert "notification" in result.events[0].data
```

See [[docs/testing/assertions|Testing Assertions]] for SSE testing details.

## Next Steps

- [[docs/streaming/html-streaming|Streaming HTML]] -- Progressive page rendering
- [[docs/templates/fragments|Fragments]] -- How fragments are rendered
- [[docs/testing/assertions|Assertions]] -- Testing SSE endpoints
