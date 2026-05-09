# Realtime Product Patterns

Use `EventStream` for post-load server push: notifications, counters, live
tails, status panels, and dashboards. Use `Suspense` or `Stream` for initial
page load. If the user should see the first page without opening a second
connection, it is not an SSE job yet.

## Shell Placement

Place long-lived SSE listeners in stable shell or layout regions, not inside
boosted content that navigation will replace:

```html
<body>
  <main id="main" hx-boost="true" hx-target="#main" hx-select="#page-content">
    {% block page_content %}{% endblock %}
  </main>

  <div hx-ext="sse"
       sse-connect="{{ url_for('notifications.stream') }}"
       hx-disinherit="hx-target hx-swap">
    <span sse-swap="notification_count"></span>
  </div>
</body>
```

`hx-disinherit` matters when a parent shell sets broad `hx-target` or
`hx-swap`. Without it, an SSE payload can inherit navigation swap policy and
replace the wrong node.

## OOB Targets

Use OOB swaps for shell state that changes alongside the current page:
notification badges, unread counts, sidebar summaries, and theme state.

Register OOB regions when they are part of the shell contract. Missing
non-optional OOB blocks should fail loudly; optional regions are for genuinely
conditional shell surfaces, not typo suppression.

Avoid `transition:true` and `view-transition-name` on containers that receive
OOB descendants. Put transitions on narrow navigation links or detail elements
that are not updated by SSE/OOB.

## Event Identity And Replay

Production-critical streams need a replay policy before launch. Browsers send
`Last-Event-ID` after reconnect when the stream yields events with `id:`. Chirp
supports `SSEEvent(id=...)`; the product owns the cursor.

Good event ids are domain cursors:

- post id within a thread;
- monotonically increasing notification id for a user;
- changelog sequence for a dashboard scope;
- durable message id from a queue or database.

Weak event ids are process-local counters, timestamps without ordering
guarantees, or random values that cannot be queried after reconnect.

Handler pattern:

```python
from chirp import EventStream, SSEEvent


async def stream(request):
    last_id = request.headers.get("last-event-id")

    async def events():
        async for item in missed_items_after(last_id):
            yield SSEEvent(event="post", id=str(item.id), data=item.html)
        async for item in live_items():
            yield SSEEvent(event="post", id=str(item.id), data=item.html)

    return EventStream(events())
```

Chirp's integration suite covers this pattern with reconnect and fresh-tab
cases; durable cursor storage remains product-owned.

If missed events cannot be replayed, document the degradation. Common fallback:
send an event that tells the client to refresh the affected fragment or page.

## Heartbeats And Disconnects

Long-lived streams need cleanup:

- send heartbeats or ping events so proxies and clients notice dead
  connections;
- remove presence entries on disconnect;
- expire presence by TTL as a backup for unclean disconnects;
- decide whether duplicate tabs count once or many times;
- keep per-event render failures isolated so one bad fragment does not kill the
  whole stream.

## Test Matrix

At product scale, test more than "the endpoint returns text/event-stream":

- first event is a ping or no-op when the page already rendered the same data;
- SSE listener lives outside boosted content and survives navigation;
- OOB targets exist on pages that should receive the update;
- `Last-Event-ID` returns only missed events after reconnect;
- duplicate tabs do not corrupt presence or unread state;
- closing a tab triggers cleanup or expires by TTL;
- malformed event payloads emit an error event without terminating unrelated
  connections.

Use browser smoke for shell/OOB behavior. Unit tests can prove event framing,
but only a browser catches htmx inheritance, view-transition flicker, and
replaced listeners.
