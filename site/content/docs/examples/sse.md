---
title: SSE
description: Minimal Server-Sent Events with strings, SSEEvent, and Fragment payloads
draft: false
weight: 50
lang: en
type: doc
tags: [examples, sse, eventstream, realtime]
keywords: [sse, server sent events, eventstream, fragments]
category: examples
---

## Live feed over SSE

This example streams HTML to the browser *after* the page loads — a feed of
notifications that appear one by one, with no client-side JavaScript. You return
an `EventStream` from a route, and an async generator yields events over a
long-lived connection. Each yielded value can be a plain string, a structured
`SSEEvent` (custom event name and id), or a rendered `Fragment(...)` that htmx
swaps into the page.

:::{tip} Updates after load, or slow data on first paint?
Reach for SSE when updates arrive *after* the initial render — notifications, a
ticker, a chat tail. For slow data on the *first* paint, use Suspense instead.
See [[docs/build-apps/streaming-updates/_index|the streaming decision table]].
:::

## Minimal example

Two routes: one renders the page shell, the other returns an `EventStream` whose
generator yields a mix of `SSEEvent` and `Fragment` values.

```python
import asyncio
from pathlib import Path

from chirp import App, AppConfig, EventStream, Fragment, SSEEvent, Template

config = AppConfig(
    template_dir=Path(__file__).parent / "templates",
    worker_mode="async",
    sse_close_event="close",
)
app = App(config=config)

_NOTIFICATIONS = [
    {"title": "Welcome", "message": "You are now connected to the live feed."},
    {"title": "Update", "message": "New deployment started."},
    {"title": "Alert", "message": "CPU usage above 90% on worker-3."},
    {"title": "Resolved", "message": "CPU usage back to normal."},
]


@app.route("/")
def index():
    return Template("feed.html")


@app.route("/events", referenced=True)
def events():
    async def generate():
        # Structured SSEEvent — custom event name, kept off the htmx message channel.
        yield SSEEvent(data="connected", event="status")

        # Fragment events — rendered HTML pushed to the browser and swapped by htmx.
        for notification in _NOTIFICATIONS:
            await asyncio.sleep(1.5)
            yield Fragment(
                "feed.html",
                "notification",
                title=notification["title"],
                message=notification["message"],
            )

    return EventStream(generate())


if __name__ == "__main__":
    app.run()
```

*Source: [`examples/standalone/sse/app.py`](https://github.com/lbliii/chirp/blob/main/examples/standalone/sse/app.py).*

Set `worker_mode="async"` — the stream holds a connection open and awaits between
events. This maintained example follows Chirp's htmx 2 default: a `Fragment`'s
target becomes the named event consumed by `sse-swap`. The exact htmx 4 preview
instead emits `hx-sse:connect`; its rendered fragments are unnamed HTML and an
explicit target becomes a DOM id inside `<hx-partial>`. Named `SSEEvent`s remain
literal DOM events. See the SSE guide for the side-by-side migration contract.

## Run it

::::{steps}
:::{step} Start the app
```bash
PYTHONPATH=src python examples/standalone/sse/app.py
```
Open `http://127.0.0.1:8000/` and watch notifications stream in.
:::{/step}
:::{step} Run the test
```bash
pytest examples/standalone/sse/
```
:::{/step}
::::{/steps}

:::{note}
A failing `Fragment` render does not kill the open stream. The event boundary is
per-event: one bad block logs an error and emits an error event, and the
connection stays alive for the next one.
:::

:::{dropdown} What the contract checks cover here
These checks run at startup via `app.check()` — they are static analysis of your
routes and templates, separate from the per-event runtime boundary described
above.

- **Event cross-references (`sse_crossref`).** Each `sse-swap` target in the markup
  is matched against the event names the connected route emits — the `target` on a
  `Fragment(...)`, the `event` on an `SSEEvent(...)`, and any declared
  `SSEContract.event_types`. A target that no event produces is flagged as a likely
  typo.
- **Self-swap (`sse_self_swap`).** An `sse-swap` on the *same* element as
  `sse-connect` never matches (htmx excludes the root element), so it errors.
- **Connect scope (`sse_scope`).** An `sse-connect` inside a broad `hx-target`
  scope without mitigation errors, since inherited swaps would clobber the wrong
  region.

See [[docs/about/core-concepts/contracts|how contract checks work]].
:::{/dropdown}

:::{note} See also
- [[docs/build-apps/streaming-updates/server-sent-events|Server-Sent Events guide]] — the full `EventStream` and `SSEEvent` API.
- [[docs/build-apps/streaming-updates/sse-patterns|SSE patterns]] — reconnects, channels, and reactive templates.
- [[docs/build-apps/streaming-updates/_index|Streaming overview]] — Suspense vs SSE vs Stream.
- [[docs/about/core-concepts/return-values|Return values]] — how each return type maps to an intent.
- [[docs/quality/testing/assertions|Testing assertions]] — assert against streamed HTML.
:::
