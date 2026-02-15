"""Static Site Dev Server — live reload with chirp + pounce.

Demonstrates a static site served through chirp with:
- Root-level StaticFiles middleware (prefix="/")
- HTMLInject middleware for live-reload script injection
- SSE endpoint for signalling reloads to the browser

This is the pattern that Bengal (or any static site generator) can
adopt when migrating to chirp + pounce.

Run:
    python app.py
"""

import asyncio
from pathlib import Path

from chirp import App, EventStream, SSEEvent
from chirp.middleware import HTMLInject, StaticFiles

PUBLIC_DIR = Path(__file__).parent / "public"

app = App()

# ---------------------------------------------------------------------------
# SSE reload endpoint — clients listen here for reload signals
# ---------------------------------------------------------------------------

_reload_event = asyncio.Event()


@app.route("/__reload__", referenced=True)
def reload_events():
    """Stream reload events over SSE.

    Each connected browser tab keeps an open connection here.
    When ``_reload_event`` is set the generator yields a reload
    event and the client-side script reloads the page.
    """

    async def stream():
        while True:
            await _reload_event.wait()
            _reload_event.clear()
            yield SSEEvent(data="reload", event="reload")

    return EventStream(stream())


# ---------------------------------------------------------------------------
# Middleware stack (order matters: first added = outermost)
# ---------------------------------------------------------------------------

# 1. Inject a tiny live-reload script into every HTML response
_RELOAD_SCRIPT = """\
<script>
(function() {
  var es = new EventSource("/__reload__");
  es.addEventListener("reload", function() { location.reload(); });
  es.onerror = function() { setTimeout(function() { location.reload(); }, 2000); };
})();
</script>"""

app.add_middleware(HTMLInject(_RELOAD_SCRIPT))

# 2. Serve the static site from ./public at the root
app.add_middleware(StaticFiles(
    directory=PUBLIC_DIR,
    prefix="/",
    not_found_page="404.html",
    cache_control="no-cache",
))


if __name__ == "__main__":
    app.run()
