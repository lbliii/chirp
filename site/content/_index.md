---
title: Chirp
description: A hypermedia-native Python framework with typed returns and contract checks for server-rendered product UIs
template: home.html
weight: 100
type: page
draft: false
lang: en
keywords: [chirp, python web framework, htmx, html over the wire, html fragments, server-rendered, streaming, sse]
category: home

# Hero configuration
blob_background: true

# CTA Buttons
cta_buttons:
  - text: Build the Five-Minute App
    url: /docs/get-started/
    style: primary
  - text: See a Live Chirp App
    url: https://luckycat-production.up.railway.app
    style: secondary

show_recent_posts: false
---

## One Template. Every Interaction. Checked Before Deploy.

**Build dynamic Python UIs without building a SPA.**

Chirp is the hypermedia-native Python framework for server-rendered product UIs.
Typed route returns produce full pages, htmx fragments, streaming HTML, and live
SSE updates from the same named template blocks. `chirp check` catches broken
routes, blocks, and targets before users do.

```python
from chirp import App, Page, Request

app = App()

@app.route("/search")
def search(request: Request):
    query = request.query.get("q", "")
    return Page("search.html", "results", query=query)
    # Browser navigation -> full page
    # htmx request      -> just the "results" block
```

No SPA. No duplicated partials. No JavaScript build pipeline.

---

## Why Build With Chirp

:::{cards}
:columns: 2
:gap: medium

:::{card} One Render Surface
:icon: layers
Use the same named template blocks for full pages, htmx fragments, OOB updates,
deferred content, and SSE payloads.
:::{/card}

:::{card} Typed Intent
:icon: code
Return `Page`, `Fragment`, `Suspense`, or `EventStream`. Chirp handles content
negotiation and htmx awareness without manual response branching.
:::{/card}

:::{card} Verified UI Wiring
:icon: shield
`chirp check` validates routes, template blocks, htmx targets, OOB regions, and
SSE wiring before users discover the mistake.
:::{/card}

:::{card} Streaming and Live Updates
:icon: zap
Send the shell first with `Suspense`, stream progressive HTML, or push rendered
fragments after load with `EventStream` and SSE.
:::{/card}

:::{card} No Frontend Build Pipeline
:icon: network
Build interactive product surfaces with Python, HTML, CSS, htmx, and browser-native
features. Add Alpine.js or isolated islands only where local state earns its keep.
:::{/card}

:::{card} Python 3.14 Native
:icon: cpu
Designed for Python 3.14 and free-threading. Covered framework paths are exercised
in free-threaded CI with explicit state and concurrency boundaries.
:::{/card}

:::{/cards}

## Where Chirp Fits

- Authenticated SaaS and internal tools where HTML is the product surface
- CRUD workflows that must work as plain forms and htmx-enhanced interactions
- Live dashboards, feeds, and operational consoles
- AI interfaces that stream tokens, tool activity, and rendered results
- Teams that want server-owned UI without duplicating page and partial templates

Chirp is deliberately focused. Choose an API-first framework when the primary
product surface is JSON, or a batteries-included platform when you need a bundled
ORM, generated admin, and its ecosystem. See [[docs/about/comparison|When to Use
Chirp]] and [[docs/about/non-goals|Non-Goals]] for the honest boundaries.

---

## Return Values, Not Response Construction

Route functions return *values*. The framework handles content negotiation based on the type:

```python
return "Hello"                                   # -> 200, text/html
return {"users": [...]}                          # -> 200, application/json
return Template("page.html", title="Home")       # -> 200, rendered via kida
return Fragment("page.html", "results", items=x) # -> 200, rendered block
return Stream("dashboard.html", **async_ctx)     # -> 200, streamed HTML
return EventStream(generator())                  # -> SSE stream
return Response(body=b"...", status=201)          # -> explicit control
return Redirect("/login")                        # -> 302
```

No `make_response()`. No `jsonify()`. The type *is* the intent.

---

## A Small Python Foundation

Chirp uses [Kida](https://lbliii.github.io/kida) for block-aware rendering and
[Pounce](https://lbliii.github.io/pounce) as its ASGI server. They arrive as normal
Python dependencies; you do not need to learn a larger ecosystem before building
your first app. Read [[docs/about/ecosystem|the ecosystem map]] when you want the
implementation details.

**Python-native. Free-threading ready. No npm required.**
