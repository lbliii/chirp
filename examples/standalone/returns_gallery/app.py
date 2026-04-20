"""Returns Gallery — every Chirp response type on one page.

Read this example first. Each route returns a different response type,
with a comment naming when to use it. Hit '/' in a browser and click
through the gallery; hit the same URLs with htmx (HX-Request header) to
see content negotiation in action.

Run:
    PYTHONPATH=src python examples/standalone/returns_gallery/app.py
"""

import asyncio
import random
from dataclasses import dataclass
from pathlib import Path

from chirp import (
    App,
    AppConfig,
    EventStream,
    Fragment,
    MutationResult,
    OOB,
    Page,
    Redirect,
    Request,
    SSEEvent,
    Stream,
    Suspense,
    Template,
    ValidationError,
)

TEMPLATES_DIR = Path(__file__).parent / "templates"

config = AppConfig(
    template_dir=TEMPLATES_DIR,
    worker_mode="async",
    debug=True,
)
app = App(config=config)


# ---------------------------------------------------------------------------
# Index — links to every gallery route, rendered as a full page.
# ---------------------------------------------------------------------------


@app.route("/")
def index():
    """Template — full-page render, no content negotiation.

    Use when: the route *always* returns a full HTML page (home, about,
    static content). If you want htmx to get a fragment and browsers to
    get a full page from the same route, use Page instead.
    """
    return Template("gallery.html", routes=_ROUTES)


# ---------------------------------------------------------------------------
# Fragment — a named block, never a full page.
# ---------------------------------------------------------------------------


@app.route("/fragment")
def fragment_demo():
    """Fragment — render a named block independently.

    Use when: the route is only ever called by htmx (or another fragment
    consumer). Returns just the block — no layout, no <html>.
    """
    return Fragment("gallery.html", "demo_fragment", value=random.randint(1, 100))


# ---------------------------------------------------------------------------
# Page — auto-negotiates: fragment for htmx, full page for browsers.
# ---------------------------------------------------------------------------


@app.route("/page")
def page_demo():
    """Page — fragment for htmx requests, full page for browser navigation.

    Use when: the same URL must serve both a standalone page and an htmx
    swap. Same template, same data, the framework picks the right shape
    based on the HX-Request header.
    """
    return Page("gallery.html", "demo_page", value=random.randint(1, 100))


# ---------------------------------------------------------------------------
# OOB — multi-target swap: primary fragment + out-of-band updates.
# ---------------------------------------------------------------------------


@app.route("/oob", methods=["POST"])
def oob_demo():
    """OOB — primary fragment plus out-of-band swaps to unrelated regions.

    Use when: one mutation needs to update multiple disjoint regions
    (e.g. a saved row + a counter + a toast). htmx consumes the primary
    swap and applies each OOB chunk to its target id.
    """
    value = random.randint(1, 100)
    return OOB(
        Fragment("gallery.html", "demo_oob_primary", value=value),
        Fragment("gallery.html", "demo_oob_counter", target="oob-counter", value=value),
    )


# ---------------------------------------------------------------------------
# Stream — flush blocks as they complete, single chunked response.
# ---------------------------------------------------------------------------


async def _load_top() -> dict:
    await asyncio.sleep(0.2)
    return {"title": "Top section", "value": random.randint(1, 100)}


async def _load_middle() -> dict:
    await asyncio.sleep(0.5)
    return {"title": "Middle section", "value": random.randint(1, 100)}


async def _load_bottom() -> dict:
    await asyncio.sleep(0.8)
    return {"title": "Bottom section", "value": random.randint(1, 100)}


@app.route("/stream")
def stream_demo():
    """Stream — flush sections as each resolves, inside one HTTP response.

    Use when: the first byte is slow but independent sections can paint
    progressively (SEO-friendly streaming render). Contrast with
    Suspense, which ships the *shell* first and streams deferred blocks
    as OOB swaps.
    """
    return Stream(
        "gallery_stream.html",
        top=_load_top(),
        middle=_load_middle(),
        bottom=_load_bottom(),
    )


# ---------------------------------------------------------------------------
# Suspense — shell first, deferred blocks stream as OOB swaps.
# ---------------------------------------------------------------------------


async def _load_stats() -> dict:
    await asyncio.sleep(0.6)
    return {"users": random.randint(100, 999), "sessions": random.randint(500, 2000)}


async def _load_feed() -> list[dict]:
    await asyncio.sleep(1.0)
    return [{"id": i, "msg": f"event {i}"} for i in range(5)]


@app.route("/suspense")
def suspense_demo():
    """Suspense — shell renders instantly, slow data streams in after.

    Use when: a dashboard or detail page has multiple slow data sources
    and you want one round trip with an instant shell. Deferred
    awaitables show skeleton placeholders, then get replaced via OOB
    swaps as each resolves.
    """
    return Suspense(
        "gallery_suspense.html",
        title="Suspense demo",
        stats=_load_stats(),
        feed=_load_feed(),
    )


# ---------------------------------------------------------------------------
# EventStream — SSE channel for post-load real-time updates.
# ---------------------------------------------------------------------------


@app.route("/events", referenced=True)
def events():
    """EventStream — Server-Sent Events, long-lived channel.

    Use when: the page has already loaded and you need to push updates
    (notifications, tickers, chat tails). NOT for initial render —
    Suspense is for that. Each yielded Fragment is rendered as an SSE
    event and swapped into the page by htmx.
    """

    async def generate():
        yield SSEEvent(data="connected", event="status")
        for i in range(5):
            await asyncio.sleep(0.8)
            yield Fragment(
                "gallery.html",
                "demo_sse_item",
                index=i,
                value=random.randint(1, 100),
            )

    return EventStream(generate())


# ---------------------------------------------------------------------------
# ValidationError — 422 + re-rendered form fragment.
# ---------------------------------------------------------------------------


@dataclass
class _Form:
    name: str = ""
    email: str = ""


@app.route("/validate", methods=["POST"])
async def validate_demo(request: Request):
    """ValidationError — 422 status with the form fragment re-rendered.

    Use when: a form submission fails server-side validation. Returns
    the form block with error state so htmx swaps the failure view in
    place. Pass retarget='#error-banner' to route errors to a different
    DOM node than the trigger.
    """
    form_data = await request.form()
    form = _Form(
        name=(form_data.get("name") or "").strip(),
        email=(form_data.get("email") or "").strip(),
    )
    errors: dict[str, str] = {}
    if not form.name:
        errors["name"] = "Name is required."
    if "@" not in form.email:
        errors["email"] = "Valid email required."
    if errors:
        return ValidationError(
            "gallery.html",
            "demo_form",
            errors=errors,
            form=form,
        )
    return Fragment("gallery.html", "demo_form_ok", form=form)


# ---------------------------------------------------------------------------
# MutationResult — progressive enhancement for mutations.
# ---------------------------------------------------------------------------


_counter = {"n": 0}


@app.route("/mutate", methods=["POST"])
def mutate_demo():
    """MutationResult — one handler, three UX flows.

    Use when: a mutation must work identically for htmx + fragments,
    htmx without fragments (HX-Redirect), and plain form POST
    (303 redirect). No branching on request headers in your handler.
    """
    _counter["n"] += 1
    return MutationResult(
        "/",  # fallback redirect target for non-htmx
        Fragment(
            "gallery.html",
            "demo_mutation_counter",
            target="mutation-counter",
            count=_counter["n"],
        ),
        trigger="counterChanged",
    )


# ---------------------------------------------------------------------------
# Redirect — plain HTTP redirect.
# ---------------------------------------------------------------------------


@app.route("/redirect")
def redirect_demo():
    """Redirect — plain HTTP 302/303, no content negotiation.

    Use when: you need an unconditional redirect (post-login, legacy
    URL). For mutations that need to work with both htmx and plain
    forms, use MutationResult instead — it handles HX-Redirect for you.
    """
    return Redirect("/", status=303)


# ---------------------------------------------------------------------------
# Route index used by the landing page.
# ---------------------------------------------------------------------------


_ROUTES = [
    ("/", "Template", "Full-page render — no content negotiation"),
    ("/fragment", "Fragment", "Named block, never a full page"),
    ("/page", "Page", "Fragment for htmx, full page for browser"),
    ("/oob", "OOB (POST)", "Multi-target swap: primary + out-of-band"),
    ("/stream", "Stream", "Flush sections as each completes"),
    ("/suspense", "Suspense", "Shell first, deferred blocks stream in"),
    ("/events", "EventStream", "SSE channel for post-load updates"),
    ("/validate", "ValidationError (POST)", "422 + re-rendered form fragment"),
    ("/mutate", "MutationResult (POST)", "One handler, three UX flows"),
    ("/redirect", "Redirect", "Plain HTTP redirect"),
]


if __name__ == "__main__":
    app.run()
