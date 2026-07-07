"""Chirp DevTools lifecycle compatibility proof for htmx 2 and htmx 4."""

import asyncio
import threading
from pathlib import Path

from chirp import (
    OOB,
    App,
    AppConfig,
    EventStream,
    Fragment,
    Request,
    Response,
    SSEEvent,
    Template,
)
from chirp.middleware.csp_nonce import CSPNonceMiddleware

TEMPLATES_DIR = Path(__file__).parent / "templates"
PREVIEW_TEMPLATES_DIR = Path(__file__).parent / "preview_templates"
SIGNAL_PREVIEW_TEMPLATES_DIR = Path(__file__).parent / "signal_preview_templates"

TIMING_LISTENER_JS = b"""window.__timingEvents = [];
function timingMarker(event, attribute) {
  var target = event.target;
  if (!target || !target.matches) return null;
  if (target.matches("#timing-result[" + attribute + "]")) return target;
  return target.querySelector("#timing-result[" + attribute + "]");
}
document.addEventListener("htmx:before:settle", function (event) {
  var marker = timingMarker(event, "data-after-swap-event");
  if (!marker) return;
  window.__timingEvents.push({
    phase: "before-settle", event: marker.dataset.afterSwapEvent, target: marker.id
  });
});
document.addEventListener("htmx:after:settle", function (event) {
  var marker = timingMarker(event, "data-after-settle-event");
  if (!marker) return;
  window.__timingEvents.push({
    phase: "after-settle", event: marker.dataset.afterSettleEvent, target: marker.id
  });
});
document.addEventListener("DOMContentLoaded", function () {
  var source = document.getElementById("sse-source");
  if (!source) return;
  source.addEventListener("notice", function (event) {
    document.body.dataset.sseNotice = event.detail.data;
  });
});
"""

SSE_HOLD_CLEANED = threading.Event()

# Each page provisions its selected htmx build explicitly. Chirp still owns the
# debug runtime and every server response remains a typed HTML return value.
app = App(
    config=AppConfig(
        template_dir=TEMPLATES_DIR,
        htmx=False,
        debug=True,
        islands=True,
        view_transitions=True,
    )
)

preview_app = App(
    config=AppConfig(
        template_dir=PREVIEW_TEMPLATES_DIR,
        htmx=True,
        htmx_version="4.0.0-beta5",
        debug=True,
        sse_retry_ms=100,
    )
)
preview_app.add_middleware(CSPNonceMiddleware(style_unsafe_inline=True))

signal_preview_app = App(
    config=AppConfig(
        template_dir=SIGNAL_PREVIEW_TEMPLATES_DIR,
        htmx=True,
        htmx_version="4.0.0-beta5",
        debug=True,
    )
)


@signal_preview_app.signal("preview_balance", initial=lambda: 0)
async def preview_balance():
    if False:
        yield 0


def _page_context(*, version: str, compat: bool) -> dict[str, object]:
    return {
        "version": version,
        "compat": compat,
        "result": "Ready",
        "count": 0,
        "target_raw": "",
        "target_id": "",
        "source_raw": "",
        "source_id": "",
        "source_tag": "",
        "trigger": "",
        "trigger_name": "",
        "request_type": "",
        "accept": "",
    }


@app.route("/")
def index():
    return Template("index.html", **_page_context(version="2", compat=False))


@app.route("/v4")
def htmx4():
    return Template("index.html", **_page_context(version="4", compat=False))


@app.route("/v4-compat")
def htmx4_compat():
    return Template("index.html", **_page_context(version="4", compat=True))


@app.route("/inspect", methods=["POST"])
def inspect(request: Request):
    return Fragment(
        "index.html",
        "metadata",
        target_raw=request.htmx_target or "",
        target_id=request.htmx_target_id or "",
        source_raw=request.htmx_source or "",
        source_id=request.htmx_source_id or "",
        source_tag=request.htmx_source_tag or "",
        trigger=request.htmx_trigger or "",
        trigger_name=request.htmx_trigger_name or "",
        request_type=request.htmx_request_type or "",
        accept=request.headers.get("accept", ""),
    )


@app.route("/swap", methods=["POST"])
def swap():
    return OOB(
        Fragment("index.html", "result", result="Swapped"),
        Fragment("index.html", "counter", target="counter", swap="outerHTML", count=1),
    )


@app.route("/failure", methods=["POST"])
def failure():
    return Response(b'<p id="failed">Server failed</p>', status=503, content_type="text/html")


@preview_app.route("/")
def preview_index():
    return Template(
        "preview.html",
        result="Ready",
        after_swap_event="",
        after_settle_event="",
        item_id="",
        item="",
    )


@signal_preview_app.route("/")
def preview_signals():
    return Template("signals.html")


@preview_app.route("/swap", methods=["POST"])
def preview_swap():
    return Fragment("preview.html", "result", result="Swapped")


@preview_app.route("/inherit")
def preview_inherit():
    return Fragment("preview.html", "inherited", inherited="Inherited")


@preview_app.route("/validation")
def preview_validation():
    return Response(
        b'<div id="validation">Validation failed</div>',
        status=422,
        content_type="text/html",
    )


@preview_app.route("/failure")
def preview_failure():
    return Response(
        b'<main id="shell">Shell destroyed</main>',
        status=500,
        content_type="text/html",
    )


@preview_app.route("/oob")
def preview_oob():
    return OOB(
        Fragment("preview.html", "main_result", result="Main updated"),
        Fragment(
            "preview.html",
            "oob_result",
            target="oob-result",
            swap="innerHTML",
            result="OOB updated",
        ),
    )


@preview_app.route("/delete", methods=["DELETE"])
async def preview_delete(request: Request):
    form = await request.form()
    item = request.query.get("item") or form.get("item", "missing")
    return Fragment("preview.html", "delete_result", item=item)


@preview_app.route("/slow")
async def preview_slow():
    await asyncio.sleep(0.2)
    return Fragment("preview.html", "slow_result", result="Too late")


@preview_app.route("/queue", methods=["POST"])
async def preview_queue():
    await asyncio.sleep(0.15)
    return Fragment("preview.html", "queue_result", result="Queued")


@preview_app.route("/history/next")
def preview_history():
    return Fragment("preview.html", "history", result="History next")


@preview_app.route("/timing")
def preview_timing():
    return Fragment(
        "preview.html",
        "timing_result",
        after_swap_event="dom-updated",
        after_settle_event="ui-settled",
    )


@preview_app.route("/timing.js")
def preview_timing_js():
    return Response(TIMING_LISTENER_JS, content_type="application/javascript; charset=utf-8")


@preview_app.route("/events", referenced=True)
def preview_events(request: Request):
    async def generate():
        if request.headers.get("last-event-id") == "3":
            yield Fragment(
                "preview.html",
                "sse_feed_item",
                target="sse-feed",
                swap="beforeend",
                item_id="sse-feed-two",
                item="feed two",
            )
            yield SSEEvent(data="complete", event="done")
            return
        yield Fragment("preview.html", "sse_main", sse_message="main one")
        yield Fragment(
            "preview.html",
            "sse_feed_item",
            target="sse-feed",
            swap="beforeend",
            item_id="sse-feed-one",
            item="feed one",
        )
        yield SSEEvent(
            data='<div id="sse-status" hx-swap-oob="innerHTML">OOB one</div>',
            id="2",
        )
        yield SSEEvent(data="named payload", event="notice")
        # Keep native EventSource reconnect proof fast on loaded CI runners.
        yield SSEEvent(data="cursor", event="cursor", id="3", retry=100)
        # A clean EOF makes reconnect behavior independent from the separate
        # generator-error event below.
        return

    return EventStream(generate())


@preview_app.route("/events/error", referenced=True)
def preview_error_events():
    async def generate():
        yield SSEEvent(data="before error", event="probe")
        raise RuntimeError("intentional SSE generator error proof")

    return EventStream(generate())


@preview_app.route("/events/hold", referenced=True)
def preview_hold_events():
    SSE_HOLD_CLEANED.clear()

    async def generate():
        try:
            yield Fragment("preview.html", "sse_hold", hold_message="connected")
            await asyncio.Event().wait()
        finally:
            SSE_HOLD_CLEANED.set()

    return EventStream(generate())


@preview_app.route("/events/hold-state", referenced=True)
def preview_hold_state():
    return Response("closed" if SSE_HOLD_CLEANED.is_set() else "open")


@signal_preview_app.route("/signals/set", methods=["POST"], referenced=True)
def preview_signal_set(request: Request):
    raw = request.query.get("value")
    value: object = "" if raw is None else int(raw)
    signal_preview_app.emit("preview_balance", value)
    return Response(b"", status=204)


if __name__ == "__main__":
    app.run()
