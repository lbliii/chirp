---
title: Early Hints (103)
description: Speed up first paint with HTTP 103 Early Hints via the Link/preload header convention
draft: false
weight: 50
lang: en
type: doc
tags: [middleware, pipeline, performance, preload, early-hints]
keywords: [early hints, 103, preload, preconnect, link header, RFC 8297, first paint]
category: guide
---

## What Early Hints do

HTTP **103 Early Hints** ([RFC 8297](https://www.rfc-editor.org/rfc/rfc8297))
is an interim response the server can send *before* the final response while it
is still computing the body. The browser uses it to start preloading or
preconnecting to the assets the page will need — CSS, JS, fonts, third-party
origins — so those fetches overlap with your server's render time instead of
waiting for the first byte of HTML.

This is most valuable on **slow-first-byte pages**: a `Suspense` dashboard, a
`Stream` page, or any route where the shell render is delayed but the page's
static assets are known up front.

## The convention: `Link` headers

Chirp has no special return type or config flag for Early Hints. The lever is a
**header convention**: set asset-preload-class `Link` headers on your response,
and Chirp's sender automatically emits a preliminary `103` frame carrying those
headers before the final response. The same `Link` headers also remain on the
final response (the 103 hint is advisory; the canonical `Link` header still
belongs on the final message).

```python
from chirp import Page

@app.route("/dashboard")
async def dashboard(request):
    return Page("dashboard.html", "content", ...).with_headers({
        "Link": "</static/app.css>; rel=preload; as=style",
    })
```

Multiple preloads use repeated `Link` headers:

```python
return Page("dashboard.html", "content").with_header(
    "Link", "</static/app.css>; rel=preload; as=style"
).with_header(
    "Link", "</static/app.js>; rel=modulepreload"
).with_header(
    "Link", "<https://cdn.example.com>; rel=preconnect"
)
```

### Which `rel=` values trigger a hint

Only asset-hint relations are promoted to the 103 frame:

| `rel=` | Use for |
| --- | --- |
| `preload` | Stylesheets, fonts, images this page needs |
| `modulepreload` | ES modules |
| `preconnect` | Warm up a connection to a third-party origin |
| `dns-prefetch` | Resolve DNS for a third-party origin |
| `prefetch` | Fetch a likely next resource |
| `prerender` | Pre-render a likely next page |

Navigational and metadata relations (`canonical`, `alternate`, `stylesheet`,
`prev`, `next`, …) are **not** promoted — they stay on the final response only.
A single `Link` header may carry more than one relation
(`rel="preconnect dns-prefetch"`); the hint fires if any token is asset-class.

## How it works on the wire

pounce 0.8.0 serializes the 103 as an interim informational response over
HTTP/1.1, HTTP/2, and HTTP/3 — it is default-on with no server flag. pounce
does **not** auto-derive the hint from your final response's `Link` headers, so
Chirp explicitly sends the extra interim frame. The interim frame carries no
body and does not commit the response, so your final status, headers, and body
flow normally afterward.

On Chirp's buffering **sync fast path**, an interim 1xx status cannot be
interleaved, so pounce transparently re-runs the request on its async worker.
The 103 still reaches the wire — no behavior is lost, only the sync shortcut for
that one request.

## Early Hints vs Speculation Rules

These two features look similar but operate at different layers and times, and
they compose cleanly:

| | Early Hints (103) | [Speculation Rules](/chirp/docs/about/core-concepts/configuration/) |
| --- | --- | --- |
| Target | The **current** response | The **next** navigation |
| Transport | Interim HTTP frame before the body | `<script type="speculationrules">` in the page body |
| Speeds up | First paint of *this* page | The user's next click |

Use Early Hints to accelerate the page being served; use Speculation Rules to
accelerate where the user goes next. Neither shares plumbing with the other.

## Verifying

Chirp's in-memory `TestClient` records only the final status and discards
interim headers, so it cannot observe the 103 frame distinctly — assert at the
ASGI sender layer (raw `send` message collector) or run a real socket. See
`tests/test_early_hints.py` for both patterns. In a browser, the DevTools
Network panel shows the early preloads starting before the document response
completes.
