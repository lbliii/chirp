---
title: Streaming HTML
description: Send a large page to the browser in chunks for a faster first paint, with no JavaScript
draft: false
weight: 10
lang: en
type: doc
tags: [streaming, html, progressive, chunked]
keywords: [stream, streaming, progressive, chunked, transfer, rendering, templatestream]
category: guide
---

## Overview

`Stream` sends a large page to the browser in chunks as each section finishes rendering, so the user sees the top of the page before the slow parts are ready. No JavaScript, no skeleton screens — just chunked transfer encoding and a template with independent sections.

Reach for `Stream` when all your data resolves reasonably fast but the template is big and you want a faster first paint.

## When to reach for it

`Stream` is one of three streaming return types. Pick by what you want the *first chunk* to be:

:::{list-table} Which streaming return type?
:header-rows: 1

* - Return type
  - First chunk
  - Use when
  - Don't use for
* - `Stream`
  - Top of the page, then sections as they finish
  - All data resolves fast; the template is large and you want a faster first paint
  - Slow data sources; updates after the page loads
* - `Suspense`
  - The shell with skeletons, then slow blocks fill in
  - Independent data sources with different load times; you want an instant shell
  - Post-load updates; pages where all data is fast
* - `TemplateStream`
  - HTML emitted as an async iterator yields (e.g. LLM tokens)
  - The template itself consumes `{% async for %}` / `{{ await }}`
  - One-shot data that's all available upfront
* - `Template`
  - The whole page at once (buffered)
  - All data is fast and you want the complete response for caching
  - Large slow-first-byte pages
:::

`Suspense` paints a shell first and fills slow blocks via out-of-band swaps — see [[docs/about/core-concepts/return-values|Return Values]] for its full story. `TemplateStream` streams a template that consumes an async iterator — covered alongside [[docs/build-apps/streaming-updates/server-sent-events|Server-Sent Events]]. For the buffered case, see [[docs/build-apps/html-fragments/rendering|standard template rendering]].

## Minimal working example

A handler returns `Stream` with a template name and context. Awaitable context values resolve concurrently *before* streaming begins, then the page chunks out top to bottom.

```python
import asyncio
from chirp import App, AppConfig, Stream

app = App(config=AppConfig(template_dir="templates", worker_mode="async"))


async def load_stats() -> list[dict[str, str | int]]:
    await asyncio.sleep(0.5)
    return [{"label": "Users", "value": 1247}, {"label": "Orders", "value": 89}]


async def load_feed() -> list[dict[str, str]]:
    await asyncio.sleep(1.0)
    return [{"title": "New order #1001", "time": "2 min ago"}]


@app.route("/")
async def index():
    return Stream(
        "dashboard.html",
        stats=load_stats(),   # pass the awaitable un-awaited
        feed=load_feed(),     # Chirp awaits both concurrently
    )
```

Pass the coroutines **un-awaited**. `Stream` gathers them concurrently before the first chunk, so the page waits on the slowest source, not the sum. Awaiting inline (`stats=await load_stats()`) defeats that concurrency — it serializes the fetches in your handler.

The HTTP response uses chunked transfer encoding. The browser renders progressively as chunks arrive — no JavaScript loading states, no skeleton screens.

## Template structure for streaming

Design the template as independent sections so each can flush as soon as its data is ready. Use [[docs/build-apps/html-fragments/rendering|standard template rendering]] — composition through a layout's `{% block content %}`, not block-level deferral.

```html
{# dashboard.html #}
<!DOCTYPE html>
<html lang="en">
<head><title>Dashboard</title></head>
<body>
  <header><h1>Dashboard</h1></header>

  <section class="stats">
    {% for s in stats %}
      <span>{{ s.label }}: <strong>{{ s.value }}</strong></span>
    {% end %}
  </section>

  <section class="feed">
    {% for item in feed %}
      <div class="feed-item">{{ item.title }} <span>{{ item.time }}</span></div>
    {% end %}
  </section>
</body>
</html>
```

A runnable version of this handler and template — plus a `TemplateStream` route — ships at [`examples/standalone/streaming`](https://github.com/lbliii/chirp/tree/main/examples/standalone/streaming).

## Gotchas

:::{warning} Capture request-scoped state before you return a streaming type
Middleware-provided helpers like `get_user()` and `csrf_token()` are backed by a `ContextVar`. Capture their values in the handler **before** returning `Stream`, `Suspense`, `TemplateStream`, or `EventStream` — don't call them during streamed template rendering or inside SSE generators.

```python
@app.route("/dashboard")
async def dashboard():
    user = get_user()        # capture in the handler
    token = csrf_token()
    return Stream("dashboard.html", current_user=user, csrf_token_value=token,
                  stats=load_stats())
```

The template then reads `current_user` / `csrf_token_value` from plain context. The request object itself is restored for chunk iteration, so `get_request()` still works — this is about middleware state (auth, session, CSRF).
:::

If a render error occurs mid-stream, the already-sent chunks stay visible and the stream closes. In production Chirp appends an opaque `<!-- chirp: render error -->` comment — no class or message leaks to the client. In `debug=True` mode it appends a visible `<div class="chirp-error">` with the traceback instead.

## Advanced

::::{dropdown} How streaming works under the hood
Kida compiles a streaming renderer alongside the standard one in the same compilation pass. When you return `Stream`:

1. Chirp resolves any awaitable context values concurrently.
2. The response goes out with `Transfer-Encoding: chunked`.
3. Kida's streaming renderer drives the template on a worker thread and yields HTML chunks as sections complete; each chunk is bridged back to the event loop, so one slow render does not stall other in-flight requests.
4. Each chunk is sent immediately via ASGI body messages.
5. The browser paints each chunk as it arrives.

For the full picture, see [[docs/build-apps/request-pipeline/render-plan|how the render pipeline builds the stream]].
::::{/dropdown}

::::{dropdown} StreamingResponse
`Stream` produces a `StreamingResponse` — a peer to `Response` for str/HTML and SSE bodies. It exposes a subset of the chainable response API: `with_status`, `with_header`, `with_headers`, `with_content_type`, `with_cookie`, and `with_render_intent`. It does **not** carry the `with_hx_*` helpers that `Response` has. Middleware can add headers to a streaming response the same way as a regular one.
::::{/dropdown}

## Suspense: shell-first with deferred blocks

When some data sources are slow and you want the page shell on screen *immediately*, reach for `Suspense` instead. It renders the shell with skeleton placeholders, then streams each block in as an out-of-band swap when its awaitable resolves. In templates, branch on `{% if key is deferred %}`. A bare `{% if key %}` on a still-deferred value raises `TypeError` and fails loudly — the deferred sentinel refuses a boolean context on purpose, so use `is deferred` to tell skeleton from loaded.

:::{note} See also

- [[docs/about/core-concepts/return-values|Return Values]] — `Suspense` semantics and the full return-type decision tree.
- [[docs/build-apps/streaming-updates/server-sent-events|Server-Sent Events]] — `TemplateStream` and post-load realtime push.
- [[examples/standalone/suspense_dashboard|suspense_dashboard example]] — minimal one-panel Suspense (start here).
- [[examples/chirpui/lucky_cat|Lucky Cat `/portfolio`]] — **advanced**: six deferred panels, explicit `defer_blocks` / `defer_map`.
:::

### Start here vs Lucky Cat advanced

| Tier | Where | When |
|------|-------|------|
| **Start here** | [[examples/standalone/suspense_dashboard|suspense_dashboard]] or the 4-line snippet in Lucky Cat `pages/portfolio/page.py` | One deferred panel; auto-discovery handles block wiring |
| **Advanced** | Lucky Cat `GET /portfolio` | Six panels, macro-nested keys, hyphenated section ids — needs `defer_blocks` + `defer_map` |

## Next steps

- [[docs/build-apps/streaming-updates/server-sent-events|Server-Sent Events]] — Real-time push updates after the page loads.
- [[docs/about/core-concepts/return-values|Return Values]] — Every return type and when to use it.
- [[docs/build-apps/html-fragments/rendering|Rendering]] — Standard buffered template rendering.

:::{related}
:::
