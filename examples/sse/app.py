"""Live Feed — Server-Sent Events with chirp.

Demonstrates real-time HTML updates: an async generator yields events
that the browser receives over SSE.  Fragment events are rendered via
kida and swapped into the page by htmx — zero client-side JavaScript.

Run:
    python app.py
"""

import asyncio
from pathlib import Path

from chirp import App, AppConfig, EventStream, Fragment, SSEEvent, Template

TEMPLATES_DIR = Path(__file__).parent / "templates"

config = AppConfig(template_dir=TEMPLATES_DIR)
app = App(config=config)

# ---------------------------------------------------------------------------
# Sample data — a small sequence of notifications
# ---------------------------------------------------------------------------

_NOTIFICATIONS = [
    {"title": "Welcome", "message": "You are now connected to the live feed."},
    {"title": "Update", "message": "New deployment started."},
    {"title": "Alert", "message": "CPU usage above 90% on worker-3."},
    {"title": "Resolved", "message": "CPU usage back to normal."},
]

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.route("/")
def index():
    """Render the feed page shell."""
    return Template("feed.html")


@app.route("/events")
def events():
    """Stream a mix of event types over SSE.

    Yields string events, structured SSEEvent objects, and kida
    Fragment objects — demonstrating all three SSE payload types.
    """

    async def generate():
        # 1. Plain string event
        yield "connected"

        await asyncio.sleep(0.05)

        # 2. Structured SSEEvent with custom type and id
        yield SSEEvent(data="heartbeat check", event="status", id="1")

        # 3. Fragment events — rendered HTML pushed to the browser
        for notification in _NOTIFICATIONS:
            await asyncio.sleep(0.05)
            yield Fragment(
                "feed.html",
                "notification",
                title=notification["title"],
                message=notification["message"],
            )

    return EventStream(generate())


if __name__ == "__main__":
    app.run()
