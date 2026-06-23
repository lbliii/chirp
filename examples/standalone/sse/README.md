# SSE

A minimal Server-Sent Events example. It shows how Chirp streams plain strings,
structured `SSEEvent` payloads, and rendered HTML fragment blocks to the browser
over a single long-lived HTTP response.

## Run

```bash
PYTHONPATH=src python examples/standalone/sse/app.py
```

Open http://127.0.0.1:8000/ and wait — notifications append every ~1.5s (override
with `SSE_DELAY=0.5` for faster demos).

## What it demonstrates

- **Lifecycle events** — `SSEEvent(..., event="status")` on a named channel separate from fragment payloads.
- **Fragment blocks over SSE** — yielded `Fragment("feed.html", "notification", ...)` renders the `{% fragment notification %}` block and pushes HTML on the default `message` channel.
- **Child sink wiring** — `sse-swap="message"` lives on a child `<div>`, not on the `sse-connect` wrapper (required for `sse_self_swap` contract compliance).

## Test

```bash
uv run pytest examples/standalone/sse/ -q
```

The suite includes `assert_sse_wired` — it catches the silent failure mode where
the page listens for one event name but the stream emits another.

## Browser smoke

1. Open `/` — placeholder reads "Waiting for events…".
2. Within a few seconds, four notification cards appear and the placeholder is removed.
3. The stream closes cleanly when the generator exhausts (no reconnect loop).
