---
title: Chirp
description: A Python web framework for the modern web platform
template: home.html
weight: 100
type: page
draft: false
lang: en
keywords: [chirp, web framework, python, htmx, fragments, streaming, sse, free-threading]
category: home

# Hero configuration
blob_background: true

# CTA Buttons
cta_buttons:
  - text: Get Started
    url: /docs/get-started/
    style: primary
  - text: API Reference
    url: /docs/reference/
    style: secondary

show_recent_posts: false
---

## HTML Over the Wire

**Fragments. Streaming. SSE. Free-threading native.**

Chirp is a Python web framework built from scratch for the modern web platform. It serves HTML beautifully -- full pages, fragments, streams, and real-time events -- all through its built-in template engine, [kida](https://lbliii.github.io/kida).

```python
from chirp import App, Template

app = App()

@app.route("/")
def index():
    return Template("index.html", title="Home")

app.run()
```

---

## What's good about it

:::{cards}
:columns: 2
:gap: medium

:::{card} Fragment Rendering
:icon: layers
Render named template blocks independently. Full page on navigation, just the fragment on htmx requests. Same template, same data, different scope.
:::{/card}

:::{card} Streaming HTML
:icon: zap
Send the page shell immediately, fill in content as data arrives. Progressive rendering over chunked transfer -- no loading spinners, no skeleton screens.
:::{/card}

:::{card} Server-Sent Events
:icon: radio
Push kida-rendered HTML fragments to the browser in real-time. Combined with htmx, this enables live UI updates with zero client-side JavaScript.
:::{/card}

:::{card} Typed Contracts
:icon: shield
`app.check()` validates every `hx-get`, `hx-post`, and `action` against the route table at startup. Broken references become compile-time errors, not runtime 404s.
:::{/card}

:::{card} Free-Threading Native
:icon: cpu
Designed for Python 3.14t from the first line. Frozen config, frozen requests, ContextVar isolation, immutable data structures. Data races are structurally impossible.
:::{/card}

:::{card} Kida Built In
:icon: code
Same author, no seam. Fragment rendering, streaming templates, and filter registration are first-class features -- not afterthoughts bolted on via extensions.
:::{/card}

:::{/cards}

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

## The Bengal Ecosystem

A structured reactive stack — every layer written in pure Python for 3.14t free-threading.

| | | | |
|--:|---|---|---|
| **ᓚᘏᗢ** | [Bengal](https://github.com/lbliii/bengal) | Static site generator | [Docs](https://lbliii.github.io/bengal/) |
| **∿∿** | [Purr](https://github.com/lbliii/purr) | Content runtime | — |
| **⌁⌁** | **Chirp** | Web framework ← You are here | [Docs](https://lbliii.github.io/chirp/) |
| **=^..^=** | [Pounce](https://github.com/lbliii/pounce) | ASGI server | [Docs](https://lbliii.github.io/pounce/) |
| **)彡** | [Kida](https://github.com/lbliii/kida) | Template engine | [Docs](https://lbliii.github.io/kida/) |
| **ฅᨐฅ** | [Patitas](https://github.com/lbliii/patitas) | Markdown parser | [Docs](https://lbliii.github.io/patitas/) |
| **⌾⌾⌾** | [Rosettes](https://github.com/lbliii/rosettes) | Syntax highlighter | [Docs](https://lbliii.github.io/rosettes/) |

Python-native. Free-threading ready. No npm required.
