"""SSE reconnect — app-owned-cursor missed-event recovery.

The browser's EventSource resends the id of the last event it saw via the
``Last-Event-ID`` header when it reconnects. Chirp READS that header and
exposes it to the generator (``request.headers.get("last-event-id")``); it
keeps NO server-side event buffer. Recovery is the app's job: this example
owns a tiny append-only event log with monotonic ids and replays only the
events whose id is greater than ``Last-Event-ID``.

Open the page, watch a few events arrive, then kill the network (or the
server) briefly. When the browser reconnects it sends the last id it saw and
the server replays only the gap — never the whole history, never duplicates.

Why ``SSEEvent`` and not a bare ``Fragment`` here: the reconnect cursor only
travels on the SSE ``id:`` field, and only ``SSEEvent`` carries an ``id``. We
render the HTML fragment with ``app.render(...)`` and ship it as the event's
``data`` so the ``id`` (the cursor), the ``event`` (the sse-swap channel), and
the rendered HTML all ride the same event.

Run:
    PYTHONPATH=src python examples/standalone/sse_reconnect/app.py
"""

import asyncio
import os
from pathlib import Path

from chirp import App, AppConfig, EventStream, Fragment, SSEEvent, Template

TEMPLATES_DIR = Path(__file__).parent / "templates"
EVENT_DELAY = float(os.environ.get("SSE_DELAY", "1.5"))

config = AppConfig(template_dir=TEMPLATES_DIR, worker_mode="async", sse_close_event="close")
app = App(config=config)

# ---------------------------------------------------------------------------
# The app owns the event log. The framework does NOT.
#
# This is the bright line: Chirp never buffers SSE events per connection.
# Recovery state lives here, in application code, where the app decides how
# much history to keep, how ids are assigned, and what a "missed" event is.
#
# Here the log is a static, monotonically-id'd sequence so the example is
# deterministic. A real app would back this with its own store (a table,
# a ring buffer, a Redis stream) and query it on reconnect.
# ---------------------------------------------------------------------------

_EVENT_LOG = (
    {"id": 1, "title": "Deploy queued", "message": "Build #481 entered the queue."},
    {"id": 2, "title": "Deploy started", "message": "Rolling out to staging."},
    {"id": 3, "title": "Tests green", "message": "All 312 checks passed."},
    {"id": 4, "title": "Promoted", "message": "Staging promoted to production."},
    {"id": 5, "title": "Healthy", "message": "Production traffic nominal."},
)


def _events_after(last_seen_id: int) -> tuple[dict, ...]:
    """The app's recovery query: only events the client has not seen.

    This is the entire recovery mechanism. There is no framework buffer to
    consult — the app decides what "after ``last_seen_id``" means against its
    own log.
    """
    return tuple(event for event in _EVENT_LOG if event["id"] > last_seen_id)


def _parse_last_event_id(raw: str | None) -> int:
    """Turn the raw Last-Event-ID header into the app's cursor.

    The header is an opaque string controlled by the client, so the app
    validates it. A fresh tab (no header) or garbage starts from 0 — the
    client receives the full log.
    """
    if raw is None:
        return 0
    try:
        return int(raw)
    except ValueError:
        return 0


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.route("/")
def index():
    """Render the feed page shell."""
    return Template("feed.html")


@app.route("/events", referenced=True)
def events(request):
    """Stream deploy events, replaying only what the client missed.

    On a fresh connection there is no ``Last-Event-ID`` header and the client
    receives the whole log. On reconnect the browser resends the last id it
    saw; the app replays only events past that cursor. Every event carries an
    ``id`` so the browser's EventSource keeps the cursor current for the next
    reconnect.
    """
    last_seen_id = _parse_last_event_id(request.headers.get("last-event-id"))

    async def generate():
        # The app's recovery query — not a framework buffer.
        for event in _events_after(last_seen_id):
            # Render the HTML fragment, then ship it as SSE data alongside the
            # id (the reconnect cursor) and the sse-swap event name. The id is
            # the only thing the browser echoes back as Last-Event-ID, and a
            # bare Fragment event has no id — so we use SSEEvent explicitly.
            html = app.render(
                Fragment(
                    "feed.html",
                    "deploy_event",
                    title=event["title"],
                    message=event["message"],
                )
            )
            yield SSEEvent(data=html, event="deploy", id=str(event["id"]))
            await asyncio.sleep(EVENT_DELAY)

        # Signal completion so htmx stops reconnecting once the log is drained.
        yield SSEEvent(data="done", event="close")

    return EventStream(generate())


if __name__ == "__main__":
    app.run()
