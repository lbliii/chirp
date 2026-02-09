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

    # Fragment -- rendered via kida, sent as SSE data
    yield Fragment("components/notification.html", message="New alert")

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
            yield Fragment("components/notification.html",
                event="notification",
                message=event.message,
                time=event.timestamp,
            )
    return EventStream(stream())
```

Client (using htmx SSE extension):

```html
<div hx-ext="sse" sse-connect="/notifications" sse-swap="notification">
  <!-- Fragments are swapped in here -->
</div>
```

The server renders HTML, the browser swaps it in. Zero client-side JavaScript for the rendering logic.

## Live Dashboard Example

A more complete example -- a dashboard that streams stats updates:

```python
@app.route("/dashboard/live")
async def live_stats():
    async def stream():
        while True:
            stats = await get_current_stats()
            yield SSEEvent(
                data=Fragment("dashboard.html", "stats_panel", stats=stats),
                event="stats-update",
            )
            await asyncio.sleep(5)  # Update every 5 seconds
    return EventStream(stream())
```

```html
<section hx-ext="sse" sse-connect="/dashboard/live">
  <div id="stats" sse-swap="stats-update">
    {# Initial stats rendered server-side #}
    {% block stats_panel %}
      ...
    {% endblock %}
  </div>
</section>
```

## Connection Lifecycle

Chirp manages the SSE connection lifecycle automatically:

1. **Event producer** -- consumes the generator, formats events, sends as ASGI body chunks
2. **Disconnect monitor** -- watches for `http.disconnect`, cancels the producer
3. **Heartbeat** -- sends `: heartbeat` comments on idle to keep the connection alive

The heartbeat uses `asyncio.shield` to avoid cancelling the pending generator coroutine when sending keep-alive comments.

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
