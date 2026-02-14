---
title: When to Use Chirp
description: Chirp's approach and when it fits
draft: false
weight: 30
lang: en
type: doc
tags: [choosing, features]
keywords: [choosing, features, htmx, fragments, streaming]
category: explanation
---

## Chirp's Approach

Chirp is built for the modern web platform: HTML over the wire, fragment rendering, streaming, and Server-Sent Events. Return values drive content negotiation — no `make_response()`, no `jsonify()`.

## What Chirp Offers

- **Fragment rendering** — Render named template blocks independently. Full page on navigation, just the fragment on htmx requests.
- **Streaming HTML** — Send the page shell immediately, fill in content as data arrives.
- **Server-Sent Events** — Push kida-rendered HTML fragments in real-time.
- **htmx integration** — First-class support for partial updates.
- **Typed contracts** — `app.check()` validates hypermedia surface at startup.
- **Kida built in** — Template engine with fragment rendering and streaming.
- **Free-threading native** — Designed for Python 3.14t.

## When to Use Chirp

Chirp is designed for:

- **htmx-driven applications** where the server renders HTML fragments
- **Real-time dashboards** with streaming HTML and SSE
- **Modern web apps** that leverage the browser's native capabilities
- **Python 3.14t** applications that want true free-threading
- **Developers who want to own their stack** — compose exactly what you need

Chirp is *not* designed for:

- JSON APIs (consider a framework built for that)
- Full-featured apps with admin panels
- Apps that need WSGI compatibility
- Teams that need maximum ecosystem support

## Next Steps

- [[docs/about/philosophy|Philosophy]] — Why Chirp makes these choices
- [[docs/get-started/quickstart|Quickstart]] — Try it yourself
- [[docs/tutorials/coming-from-flask|Coming from Flask]] — Migration guide
