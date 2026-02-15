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

The template uses normal conditional rendering for skeletons:

```html
{% block stats %}
  {% if stats %}
    {% for s in stats %}<div class="stat">{{ s.label }}: {{ s.value }}</div>{% end %}
  {% else %}
    <div class="skeleton">Loading stats...</div>
  {% end %}
{% end %}
```

How it works:

:::{steps}
:::{step} Render shell with skeletons

Sync context values render in the shell; awaitable values are set to `None` (triggering the `{% else %}` skeleton).

:::{/step}
:::{step} Send first chunk

The shell is sent immediately as the first chunk (instant first paint).

:::{/step}
:::{step} Resolve awaitables

Awaitables resolve concurrently in the background.

:::{/step}
:::{step} Stream OOB swaps

Each affected block is re-rendered with real data and sent as an out-of-band swap.

:::{/step}
:::{step} Client receives updates

For htmx navigations: OOB swaps via `hx-swap-oob`. For initial page loads: `<template>` + inline `<script>` pairs.

:::{/step}
:::{/steps}

No client-side framework needed. The browser renders the shell, and blocks fill in as data arrives.

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

- [[docs/streaming/server-sent-events|Server-Sent Events]] -- Real-time push updates
- [[docs/core-concepts/return-values|Return Values]] -- All return types
- [[docs/templates/rendering|Rendering]] -- Standard template rendering
