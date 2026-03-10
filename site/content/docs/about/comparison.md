---
title: When to Use Chirp
description: When Chirp fits, how it differs from mainstream Python web frameworks, and when to choose alternatives
draft: false
weight: 30
lang: en
type: doc
tags: [choosing, features]
keywords: [python web framework, htmx framework, fragments, streaming, flask alternative]
category: explanation
---

## Chirp's Approach

Chirp targets the modern web platform: HTML over the wire, fragment rendering,
streaming, and Server-Sent Events. If you are comparing Python web frameworks, the key
difference is Chirp's focus on server-rendered UI and fragment-based interaction rather
than JSON-first APIs.

## What Chirp Offers

- **Fragment rendering** — Render named template blocks independently. Full page on navigation, just the fragment on htmx requests.
- **Streaming HTML** — Send the page shell first, then fill in content as data arrives.
- **Server-Sent Events** — Push kida-rendered HTML fragments in real-time.
- **htmx integration** — First-class support for partial updates.
- **Typed contracts** — `app.check()` validates hypermedia surface at startup.
- **Kida built in** — Template engine with fragment rendering and streaming.
- **Free-threading native** — Designed for Python 3.14t.
- **Server-rendered by design** — Full pages, fragments, and streams come from the same templates.

## When to Use Chirp

Chirp fits teams building:

- **htmx-driven applications** where the server renders HTML fragments
- **Real-time dashboards** with streaming HTML and SSE
- **Modern web apps** that leverage the browser's native capabilities
- **Python 3.14t** applications that want true free-threading
- **Developers who want to own their stack** — compose the pieces they need
- **Teams choosing HTML-over-the-wire over SPA complexity**

Chirp is *not* the best fit for:

- JSON APIs where FastAPI or similar tools are a better fit
- Full-featured apps with admin panels where Django is a better default
- Apps that need WSGI compatibility or older deployment assumptions
- Teams that want the broadest existing ecosystem instead of a focused HTMX/server-rendered stack

## Next Steps

- [[docs/about/philosophy|Philosophy]] — Why Chirp makes these choices
- [[docs/get-started/quickstart|Quickstart]] — Try it yourself
- [[docs/tutorials/coming-from-flask|Coming from Flask]] — Migration guide
