---
title: Streaming HTML
description: Progressive page rendering with chunked transfer
draft: false
weight: 10
lang: en
type: doc
tags: [streaming, html, progressive, chunked]
keywords: [stream, streaming, progressive, chunked, transfer, rendering]
category: guide
---

## The Problem

Traditional template rendering waits for *all* data before sending anything. If your dashboard fetches stats, recent activity, and notifications, the user stares at a blank page until the slowest query finishes.

## The Solution

`Stream` renders template sections as they complete. The browser receives the page shell immediately and content fills in progressively:

```python
from chirp import Stream

@app.route("/dashboard")
async def dashboard():
    return Stream("dashboard.html",
        header=get_header(),               # Available immediately
        stats=await load_stats(),          # Streams when ready
        activity=await load_activity(),    # Streams when ready
    )
```

The HTTP response uses chunked transfer encoding. The browser renders progressively as chunks arrive -- no JavaScript loading states, no skeleton screens.

## How It Works

:::{steps}
:::{step} Compile streaming renderer

Kida's compiler generates a streaming renderer alongside the standard renderer (same compilation pass, no performance impact).

:::{/step}
:::{step} Send chunked response

When `Stream` is returned, Chirp sends the response with `Transfer-Encoding: chunked`.

:::{/step}
:::{step} Yield HTML chunks

Kida's `render_stream()` yields HTML chunks as template sections complete.

:::{/step}
:::{step} Stream to client

Each chunk is sent to the client immediately via ASGI body messages.

:::{/step}
:::{step} Progressive render

The browser renders each chunk as it arrives.

:::{/step}
:::{/steps}

```
Template:  <html> ... {% block header %} ... {% block stats %} ... {% block activity %}
Chunks:    ────────→  ──────────────────→  ──────────────→  ─────────────────────────→
Time:      0ms        50ms                 200ms            800ms
```

## Template Structure for Streaming

Design templates with independent sections that can render in any order:

```html
{# dashboard.html #}
{% extends "base.html" %}

{% block content %}
  <header>{{ header }}</header>

  <section id="stats">
    {% block stats %}
      {% for stat in stats %}
        <div class="stat">{{ stat.label }}: {{ stat.value }}</div>
      {% endfor %}
    {% endblock %}
  </section>

  <section id="activity">
    {% block activity %}
      {% for event in activity %}
        <div class="event">{{ event.description }}</div>
      {% endfor %}
    {% endblock %}
  </section>
{% endblock %}
```

## Error Handling

If an error occurs mid-stream, Chirp injects an HTML comment with the error details and closes the stream gracefully:

```html
<!-- Stream error: DatabaseConnectionError: connection timed out -->
```

The already-sent content remains visible. This is better than a full-page error for partial failures.

## StreamingResponse

Under the hood, `Stream` produces a `StreamingResponse` -- a peer to `Response` with the same chainable API:

```python
# StreamingResponse supports .with_*() methods
return Stream("dashboard.html", data=data)
# Internally becomes:
# StreamingResponse(generator, status=200, headers=...)
```

Middleware can add headers to streaming responses the same way as regular responses.

## Suspense: Instant First Paint with Deferred Blocks

`Suspense` takes streaming further. Instead of waiting for all data before rendering anything, it sends the page shell immediately with skeleton content, then fills in blocks independently as their async data resolves:

```python
from chirp import Suspense

@app.route("/dashboard")
async def dashboard():
    return Suspense("dashboard.html",
        header=site_header(),          # sync -- in the shell
        stats=load_stats(),            # awaitable -- shows skeleton first
        feed=load_feed(),              # awaitable -- shows skeleton first
    )
```

Middleware-provided helpers such as `get_user()` and `csrf_token()` are
ContextVar-backed. Capture those values in the handler before returning
`Stream`, `TemplateStream`, `Suspense`, or `EventStream`; do not call them
during streamed template rendering or inside SSE generators. The request object
itself is restored for chunk iteration, so this warning is about middleware
state such as auth/session/CSRF, not `get_request()`.

```python
@app.route("/dashboard")
def dashboard():
    user = get_user()
    token = csrf_token()
    return Suspense(
        "dashboard.html",
        current_user=user,
        csrf_token_value=token,
        stats=load_stats(),
    )
```

Then the template reads `current_user` / `csrf_token_value` from plain context
instead of calling the ContextVar-backed helpers during the stream.

Use **`{% if stats is not none %}`** for loaded vs loading — not bare `{% if stats %}`, which stays falsy for empty `tuple`/`list`/`""`/`0` after resolution and can look like a perpetual skeleton. Optionally branch on **`"stats" in __chirp_defer_pending__`** (a `frozenset` injected only by Suspense: pending key names in the shell, empty after resolution). The Python constant is **`CHIRP_DEFER_PENDING_KEY`**. The block must still **reference the context key** (e.g. `stats`) somewhere so `block_metadata().depends_on` can associate the block with that deferred key; membership in `__chirp_defer_pending__` alone is not enough for discovery.

```html
{% block stats %}
  {% if stats is not none %}
    {% for s in stats %}<div class="stat">{{ s.label }}: {{ s.value }}</div>{% end %}
  {% else %}
    <div class="skeleton">Loading stats...</div>
  {% end %}
{% end %}
```

How it works:

:::{steps}
:::{step} Render shell with skeletons

Sync context values render in the shell; awaitable values are set to `None`, and `__chirp_defer_pending__` lists their names until they resolve (use `is not none` or membership in that set for skeleton vs loaded — not truthiness alone).

:::{/step}
:::{step} Send first chunk

The shell is sent immediately as the first chunk (instant first paint).

:::{/step}
:::{step} Resolve awaitables

Awaitables resolve concurrently in the background.

:::{/step}
:::{step} Find affected blocks

Blocks to re-render are discovered via `block_metadata().depends_on` — Kida's static analysis traces which blocks reference the deferred keys. Ancestor blocks whose dependency set is a strict superset of a leaf block are pruned (they'd produce wasteful OOB chunks targeting non-existent DOM ids).

When static analysis misses a block (e.g. deferred values passed through macro arguments), set `defer_blocks` to list them explicitly:

```python
return Suspense("page.html",
    defer_blocks=("hero_stats", "sidebar_stats"),
    stats=load_stats(),
)
```

Use `defer_map` to remap block names to different DOM ids for the OOB swap target:

```python
return Suspense("page.html",
    defer_map={"stats": "stats-panel"},
    stats=load_stats(),
)
```

:::{/step}
:::{step} Stream OOB swaps

Each affected block is re-rendered with real data and sent as an out-of-band swap.

:::{/step}
:::{step} Client receives updates

For htmx navigations: OOB swaps via `hx-swap-oob`. For initial page loads: `<template>` + inline `<script>` pairs.

:::{/step}
:::{/steps}

No client-side framework needed. The browser renders the shell, and blocks fill in as data arrives.

### Reuse deferred values with `DeferredCache`

Use `DeferredCache` when the same deferred value is needed by multiple blocks
or nearby page navigations and the value can be reused for a short TTL window.
The cache is explicit app or route state: there is no process-wide default.

```python
from chirp import DeferredCache, Suspense

stars_cache = DeferredCache(default_ttl=300)

@app.route("/")
def home():
    return Suspense(
        "home.html",
        stars=stars_cache.get_or_defer(
            "gh:lbliii/chirp",
            lambda: fetch_github_stars_label("lbliii", "chirp"),
        ),
    )
```

On a cache miss, `get_or_defer()` returns an awaitable, so `Suspense` renders
the skeleton and streams the resolved block later. On a warm hit, it returns the
cached value directly, so the value renders in the initial shell and no OOB
chunk is needed. Only successful results are cached; exceptions continue
through Suspense's existing error fallback path. The factory must return an
awaitable, not a pre-created coroutine, so warm cache hits do not allocate
unused coroutine objects. `DeferredCache` does not create a browser-side store
and does not push real-time updates.

When using `mount_pages`, `Suspense` receives the layout chain automatically. The first chunk is wrapped in your `_layout.html` shell (head, CSS, sidebar), and OOB swaps target block IDs inside the page. Fragment-only requests skip the layout (same as `Page`).

**Alpine.js:** Streaming responses are still HTML documents. When `AppConfig(alpine=True)`, `AlpineInject` rewrites the chunk stream so the Alpine bundle is inserted before `</body>` in the final output—same deduplication rules as buffered pages—so shell-first routes (Suspense, skeletons) keep interactive components working without inlining scripts in layouts. If `use_chirp_ui(app)` is active, the shared `chirpui-alpine.js` runtime is also injected on full-page streaming HTML, so named chirp-ui controllers remain available there too.

## When to Use Each

Use `Suspense` when:

- A page has independent data sources with different load times
- You want instant first paint with skeleton/loading states
- Some sections load fast (navigation, layout) while others are slow (analytics, feeds)

Use `Stream` when:

- A page has multiple independent data sources with varying load times
- You want top-to-bottom progressive rendering
- Time-to-first-byte matters more than total render time

Use `Template` when:

- All data is available quickly
- The template is simple
- You need the complete response for caching or processing

## Next Steps

- [[docs/build-apps/streaming-updates/server-sent-events|Server-Sent Events]] -- Real-time push updates
- [[docs/about/core-concepts/return-values|Return Values]] -- All return types
- [[docs/build-apps/html-fragments/rendering|Rendering]] -- Standard template rendering
