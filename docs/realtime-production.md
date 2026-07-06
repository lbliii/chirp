# Realtime Product Patterns

Use `EventStream` for post-load server push: notifications, counters, live
tails, status panels, and dashboards. Use `Suspense` or `Stream` for initial
page load. If the user should see the first page without opening a second
connection, it is not an SSE job yet.

## Shell Placement

Place long-lived SSE listeners in stable shell or layout regions, not inside
boosted content that navigation will replace:

For the exact htmx 4 preview, use native fetch-stream markup with an explicit
stable target:

```html
<div hx-sse:connect="{{ url_for('notifications.stream') }}"
     hx-target="#notification-count">
  <span id="notification-count">{{ initial_count }}</span>
</div>
```

An untargeted yielded `Fragment` follows that normal target. A targeted
`Fragment(..., target="notification-count")` arrives as an unnamed
`<hx-partial>` update. Named `SSEEvent`s are application DOM events, not swaps.

The htmx 2 rollback tier keeps its legacy listener shape:

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

On htmx 2, `hx-disinherit` matters when a parent shell sets broad `hx-target` or
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

## Signals — One Connection, Many Bindings

When the same live *value* appears in more than one place — a balance in the
topbar and in a modal, an unread badge mirrored across rooms, a status pill —
reach for a signal instead of hand-maintaining OOB twins. Declare the producer
once with `@app.signal(name, ...)` (or `@app.derived(name, on=(...))`), push with
`app.emit(name, value)`, and bind it anywhere with `{{ signal('name') }}` /
`{{ signal_block('name') }}` under one `{{ signal_connect() }}` wrapper. Every
binding stays in sync from a single `/_chirp/live` connection, so an SSE-heavy
shell holds **one** connection instead of N.

Production rules:

- **Place `signal_connect()` in the stable shell, outside boosted content.** Every
  sink must be a descendant (htmx binds `sse-swap` via `querySelectorAll`). Keep
  the connect element outside `#main` so a boosted swap leaves the connection
  intact and htmx re-binds freshly-swapped sinks to the ancestor.
- **A `derived` must be a pure function of its input signal values.** Never read a
  process-local store, global, or clock inside a derived — a store read is
  non-deterministic across workers and can race a concurrent mutation on another
  thread. Pass everything the derived needs through the emitted value (a snapshot
  that bundles, e.g., the rows and the unread count atomically), so a derived
  badge can never disagree with the list it summarizes.
- **Let `app.check()` enforce bindings.** The `signal_dead_binding` (ERROR) rule
  catches a binding with no producer — the dead-binding class where an element
  never updates; `signal_orphan` (INFO) catches a producer no template displays.

### Single-process constraint

The signal bus is in-process memory and the `/_chirp/live` connection is pinned to
the worker that accepted it, so the single-node `signal()` primitive that ships
today is **single-process only**: run `workers=1` and `worker_mode="async"`. With
multiple OS-process workers each holds a separate copy of the bus and value cache —
a push on one worker is invisible to bindings served by another, and the long-lived
connection ties up a worker so page loads that land there can stall.

This is correct for a single-user demo, an internal tool, or any one-process
deployment. **Multi-worker realtime needs a shared bus backplane** (Redis /
Postgres pub-sub) plus an external state store so every worker sees the same emits
and current values. That pluggable multi-worker `SignalBus` is designed but not
shipped — see `plan/drafted/rfc-live-sse-topics.md` (§12); the surface is
classified **Provisional** in `docs/public-api.md` until it lands. If you need
cross-worker realtime today, use an `EventStream` over a product-owned durable
cursor (see *Event Identity And Replay* below), where your store is the backplane.

## Event Identity And Replay

Production-critical streams need a replay policy before launch. Browsers send
`Last-Event-ID` after reconnect when the stream yields events with `id:`. Chirp
supports `SSEEvent(id=...)`; the product owns the cursor.

The htmx 4 fetch extension sends `Last-Event-ID` on reconnect and background
resume. Chirp captures the selected SSE dialect once per connection; reconnect
creates a new request and a fresh request-scoped context.

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
