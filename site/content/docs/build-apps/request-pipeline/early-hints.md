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

Reach for Early Hints when first-byte is slow but the page's static assets are
known up front — a [[docs/build-apps/streaming-updates/html-streaming|Suspense]]
dashboard, a [[docs/build-apps/streaming-updates/html-streaming|Stream]] page, or
any route where the shell render is delayed. You opt in by setting `Link` preload
headers on the response; Chirp does the rest.

## The convention: `Link` headers

Chirp has no special return type or config flag for Early Hints. The lever is a
**header convention**: set asset-preload-class `Link` headers on the response,
and Chirp's sender automatically emits a preliminary `103` frame carrying those
headers before the final response. The same `Link` headers also remain on the
final response (the 103 hint is advisory; the canonical `Link` header still
belongs on the final message).

`Link` headers live on a `Response`. The chainable `.with_header()` method
returns a new `Response` with the header appended:

```python
from chirp import Response

# A non-preload Link silently fires no hint; rel=preload does.
response = Response("<html>...</html>").with_header(
    "Link", "</static/app.css>; rel=preload; as=style"
)
```

Handlers return [[docs/about/core-concepts/return-values|render intents]] like
`Page`, `Suspense`, or `Stream` — not a `Response` you build by hand — so the
idiomatic place to attach preload headers is
[[docs/build-apps/request-pipeline/custom|response-transforming middleware]],
which sees the rendered `Response` after the handler runs:

```python
from chirp import App, Request, Response, Suspense
from chirp.middleware.protocol import Next

app = App()

async def preload(request: Request, next: Next) -> Response:
    response = await next(request)
    if isinstance(response, Response):
        return response.with_header(
            "Link", "</static/app.css>; rel=preload; as=style"
        )
    return response

app.add_middleware(preload)

async def load_stats() -> dict[str, int]:
    ...  # slow query; deferred so the shell paints first

@app.route("/dashboard")
async def dashboard(request: Request) -> Suspense:
    return Suspense("dashboard.html", stats=load_stats())
```

Multiple preloads use repeated `.with_header("Link", ...)` calls — each value is
a separate `Link` header:

```python
return (
    response
    .with_header("Link", "</static/app.css>; rel=preload; as=style")
    .with_header("Link", "</static/app.js>; rel=modulepreload")
    .with_header("Link", "<https://cdn.example.com>; rel=preconnect")
)
```

### Which `rel=` values trigger a hint

Only asset-hint relations are promoted to the 103 frame:

:::{list-table}
:header-rows: 1

* - `rel=`
  - Use for
* - `preload`
  - Stylesheets, fonts, images this page needs
* - `modulepreload`
  - ES modules
* - `preconnect`
  - Warm up a connection to a third-party origin
* - `dns-prefetch`
  - Resolve DNS for a third-party origin
* - `prefetch`
  - Fetch a likely next resource
* - `prerender`
  - Pre-render a likely next page
:::

A single `Link` header may carry more than one relation
(`rel="preconnect dns-prefetch"`); the hint fires if any token is asset-class.

:::{warning}
Navigational and metadata relations (`canonical`, `alternate`, `stylesheet`,
`prev`, `next`) are **not** promoted. They stay on the final response only — a
`rel=stylesheet` Link will silently fire no early hint. Use `rel=preload` for
assets you want the browser to fetch ahead of the body.
:::

::::{dropdown} How it works on the wire
The serializer emits the 103 as an interim informational response over HTTP/1.1,
HTTP/2, and HTTP/3 — default-on, with no server flag. It does **not** auto-derive
the hint from your final response's `Link` headers, so Chirp explicitly sends the
extra interim frame. The interim frame carries no body and does not commit the
response, so your final status, headers, and body flow normally afterward.

On Chirp's buffering **sync fast path**, an interim 1xx status cannot be
interleaved, so the request is transparently re-run on the async worker. The 103
still reaches the wire — no behavior is lost, only the sync shortcut for that one
request.

:::{since} 0.8.0
The serializer surfaces 103 as a status convention on the response
start frame across H1/H2/H3.
:::
::::{/dropdown}

## Early Hints vs Speculation Rules

These two features look similar but operate at different layers and times, and
they compose cleanly:

:::{list-table}
:header-rows: 1

* -
  - Early Hints (103)
  - [[docs/about/core-concepts/configuration|Speculation Rules]]
* - Target
  - The **current** response
  - The **next** navigation
* - Transport
  - Interim HTTP frame before the body
  - `<script type="speculationrules">` in the page body
* - Speeds up
  - First paint of *this* page
  - The user's next click
:::

Use Early Hints to accelerate the page being served; use Speculation Rules to
accelerate where the user goes next. Neither shares plumbing with the other.

## Verifying

In a browser, the DevTools Network panel shows the early preloads starting
before the document response completes.

:::{note}
Chirp's in-memory `TestClient` records only the final status and discards interim
headers, so it cannot observe the 103 frame distinctly. To assert it in a test,
collect raw ASGI `send` messages at the sender layer, or run against a real
socket. See [`tests/test_early_hints.py`](https://github.com/lbliii/chirp/blob/main/tests/test_early_hints.py)
for both patterns.
:::

:::{note} See also
- [[docs/build-apps/request-pipeline/_index|The request pipeline]] — where Early Hints fit in the response flow
- [[docs/build-apps/streaming-updates/html-streaming|HTML streaming]] — the `Suspense` and `Stream` pages Early Hints pair with
:::
