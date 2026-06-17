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

Return an `EventStream` from a handler and Chirp holds the HTTP connection open,
formatting whatever your async generator yields as SSE wire events. Yield a
[[docs/build-apps/html-fragments/fragments|Fragment]] and the browser swaps
rendered HTML into the page in real time — no client-side render code.

Reach for `EventStream` when the page needs updates **after** it loads:
notifications, a live ticker, a dashboard tail. For a one-shot slow page that
should paint progressively on first load, use
[[docs/build-apps/streaming-updates/html-streaming|Stream or Suspense]] instead.

:::{note} See also

- [[docs/build-apps/streaming-updates/_index|Streaming and real-time overview]] — the canonical Stream vs Suspense vs EventStream decision table.
- [[docs/build-apps/streaming-updates/html-streaming|HTML streaming]] — progressive first-paint without a long-lived connection.
- [[docs/build-apps/streaming-updates/sse-patterns|SSE patterns]] — pub/sub, broadcast, and presence recipes built on `EventStream`.
:::

## EventStream

Return an `EventStream` from a route handler to start pushing events:

```python
from chirp import EventStream

@app.route("/events", referenced=True)
async def events():
    async def stream():
        while True:
            data = await get_next_update()
            yield data
    return EventStream(stream())
```

The generator yields values. Chirp formats them as SSE wire protocol and sends
them to the client. Mark SSE routes with `referenced=True` — they are reached by
a `sse-connect` attribute, not a link the contract checker can see, so the flag
keeps them out of the orphan-route report.

::::{dropdown} New to SSE? How it compares to WebSockets
Server-Sent Events are a standard browser API for receiving a stream of events
from the server over a persistent HTTP connection. Unlike WebSockets, SSE is:

- **One-directional** — server pushes to client
- **Plain HTTP** — no protocol upgrade, no special infrastructure
- **Auto-reconnecting** — the browser reconnects automatically
- **Text-based** — the simple `text/event-stream` format

Chirp leans into SSE over WebSockets on purpose; see
[[docs/about/philosophy|Philosophy]] for the stance.
::::{/dropdown}

## Yield Types

The generator can yield different types:

```python
from chirp import Fragment, SSEEvent

async def stream():
    # String -- sent as the SSE data field
    yield "Hello, World!"

    # Dict -- JSON-serialized as the SSE data field
    yield {"count": 42, "status": "ok"}

    # Fragment -- rendered via kida, sent as a named SSE event.
    # target= becomes the SSE event name; without a target the event
    # has no name and htmx routes it to the default "message" channel.
    yield Fragment("components/notification.html", "alert",
                   target="notification", message="New alert")

    # SSEEvent -- full control over event type, id, retry
    yield SSEEvent(data="custom", event="ping", id="1")
```

Yielding a `Fragment` covers the common case: the rendered HTML is the data and
`target` becomes the event name a `sse-swap` attribute can match on. Most apps
never construct `SSEEvent` directly.

::::{dropdown} SSEEvent: full field reference

For fine-grained control over the wire event — explicit `id` for reconnection,
a `retry` hint — yield `SSEEvent` objects:

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

| Field | Type | Notes |
|-------|------|-------|
| `data` | `str` | Required. The event payload. |
| `event` | `str \| None` | Event name; `sse-swap` and `addEventListener` filter on it. Single-line only. |
| `id` | `str \| None` | Echoed in the `Last-Event-ID` header on reconnect. Single-line only. |
| `retry` | `int \| None` | Reconnection interval in milliseconds. Must be non-negative. |

Chirp rejects CR/LF/NUL characters in the `event` and `id` metadata fields so
event payloads cannot inject extra wire-protocol lines.
::::{/dropdown}

## Reconnect And Replay

Browsers automatically reconnect SSE streams and send the last received event
id in the `Last-Event-ID` request header when your stream yields events with
`id:`. Chirp preserves `SSEEvent(id=...)` on the wire, but it does not store or
replay missed events for you — replay is a product concern.

::::{dropdown} Replaying missed events with a durable cursor

Production-critical streams need a product-owned durable cursor: a database
sequence, notification id, post id, queue offset, or another value that can be
queried after reconnect.

```python
from chirp import EventStream, Request, SSEEvent


@app.route("/notifications/stream", referenced=True)
async def notifications(request: Request):
    last_id = request.headers.get("last-event-id")

    async def stream():
        async for item in missed_notifications_after(last_id):
            yield SSEEvent(event="notification", id=str(item.id), data=item.html)
        async for item in live_notifications():
            yield SSEEvent(event="notification", id=str(item.id), data=item.html)

    return EventStream(stream())
```

If the product cannot replay missed events, make that degradation explicit:
send a refresh event for the affected fragment or document that reconnecting
clients may need to reload the page.
::::{/dropdown}

## Real-Time HTML with htmx

The killer pattern: combine SSE with htmx to push rendered HTML fragments in real-time.

Server:

```python
@app.route("/notifications", referenced=True)
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

:::{warning} sse-swap must be on a child element
`sse-swap` must sit on a **child** of the `sse-connect` element, not the same
element. htmx uses `querySelectorAll` internally, which does not include the
root element itself — put the swap target one level in.
:::

The server renders HTML, the browser swaps it in. Zero client-side JavaScript
for the rendering logic. See [[docs/build-apps/html-fragments/fragments|Fragments]]
for how blocks are selected and rendered.

## Live Dashboard Example

A more complete example -- a dashboard that streams stats updates:

```python
import asyncio

from chirp import Fragment

@app.route("/dashboard/live", referenced=True)
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

:::{warning} Stop layout `hx-target` from bleeding into SSE swaps
A layout-level `hx-target` (for example, one set by `hx-boost`) can override where
SSE events land — the swap lands in the inherited target and wipes the page. The
fix is explicit: set `hx-disinherit="hx-target hx-swap"` on the `sse-connect`
element, or add `hx-target="this"` on it. The built-in `sse_scope` macro wires
this for you:

```html
{% from "chirp/sse.html" import sse_scope %}
{{ sse_scope("/events", swap="time_block") }}
```

The `safe_target` middleware does **not** cover this case: it only adds
`hx-target="this"` to elements that make an `hx-get`/`hx-post`/etc. request and
declare `hx-trigger="...from:..."`. A plain `sse-connect` element matches neither,
so you must wire the mitigation yourself.
:::

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

For [[docs/build-apps/streaming-updates/reactive-system|reactive streams]], if
the `context_builder()` function itself raises (e.g., a deleted record), the
entire event is skipped and the stream waits for the next change. See
[[docs/reference/errors|Error Reference]] for the full error hierarchy.

## Worker Mode

SSE connections are long-lived: the server holds the HTTP connection open and
streams events as they arrive. The one rule to remember — **set
`worker_mode="async"` for any app that uses SSE**:

```python
config = AppConfig(worker_mode="async")
```

::::{dropdown} Advanced: why worker mode matters for long-lived connections
The default `worker_mode="auto"` selects sync workers on Python 3.14t
(free-threading) and async workers on a GIL build. Sync workers block one thread
per SSE connection, preventing that worker from handling other requests. With
async workers, SSE streams and request handlers run as concurrent tasks in the
same event loop.

This is especially important for bidirectional patterns (SSE + POST) where
in-memory pub-sub uses `asyncio.Queue` — the subscriber and emitter must share
the same event loop.

| Mode | SSE support | When to use |
|------|-------------|-------------|
| `"async"` | Full | Apps with SSE, streaming, or long-lived connections |
| `"auto"` | Falls back to ASGI | Simple request-response apps (no SSE) |
| `"sync"` | Falls back to ASGI | CPU-bound sync handlers only |

See [[docs/about/core-concepts/configuration|Configuration]] for the full
`worker_mode` and `AppConfig` reference.
::::{/dropdown}

## Connection Lifecycle

Chirp manages the SSE connection lifecycle automatically:

:::{steps}
:::{step} Event producer

Consumes the generator, formats events, sends as ASGI body chunks.

:::{/step}
:::{step} Disconnect monitor

Watches for `http.disconnect`, cancels the producer when the client disconnects.

:::{/step}
:::{step} Heartbeat

Sends `: heartbeat` comments on idle to keep the connection alive.

:::{/step}
:::{/steps}

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

See [[docs/quality/testing/assertions|Testing Assertions]] for SSE testing details.

## Next Steps

- [[docs/build-apps/streaming-updates/sse-patterns|SSE patterns]] — pub/sub, broadcast, and presence recipes.
- [[docs/build-apps/streaming-updates/reactive-system|Reactive system and signals]] — server-reactive values that fan out to SSE.
- [[docs/build-apps/streaming-updates/html-streaming|Streaming HTML]] — progressive page rendering without a long-lived connection.
- [[docs/quality/testing/assertions|Testing assertions]] — testing SSE endpoints.

:::{related}
:limit: 3
:section_title: See Also
:::
