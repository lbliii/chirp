# SSE Reconnect — App-Owned-Cursor Recovery

When a browser's `EventSource` drops and reconnects, it resends the id of the
last event it saw in the `Last-Event-ID` request header. This example shows the
**app-owned recovery** pattern: Chirp READS that header and exposes it to the
generator (`request.headers.get("last-event-id")`), but keeps **no server-side
event buffer**. The app owns a small append-only event log with monotonic ids
and replays only the events the client missed.

This is the bright line. The framework never buffers or replays SSE events
per connection — that would be per-connection server state. Recovery is an
application query against an application-owned store.

See `docs/rfcs/007-sse-last-event-id-recovery.md` for the boundary rationale.

## How It Works

- Each event is an `SSEEvent` with a monotonic `id` (the reconnect cursor) and
  an `event` name (`deploy`) that the page listens for via `sse-swap="deploy"`.
  The rendered HTML fragment rides in the event's `data`.
- A fresh tab sends no `Last-Event-ID`, so the app replays the whole log.
- A reconnect sends the last id it saw; the app's recovery query
  (`_events_after`) returns only events past that cursor — no duplicates, no
  full re-send.

The cursor only travels on the SSE `id:` field, and only `SSEEvent` carries an
`id` — a bare `Fragment` event does not. That is why this example renders the
fragment with `app.render(...)` and ships it inside an `SSEEvent`.

## Run

```bash
PYTHONPATH=src python examples/standalone/sse_reconnect/app.py
```

Open the page, watch events arrive, then briefly stop the server (or kill the
network). On reconnect the browser resends `Last-Event-ID` and only the gap is
replayed.

## Test

```bash
pytest examples/standalone/sse_reconnect/
```
