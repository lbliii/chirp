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

1. Kida's compiler generates a streaming renderer alongside the standard renderer (same compilation pass, no performance impact)
2. When `Stream` is returned, Chirp sends the response with `Transfer-Encoding: chunked`
3. Kida's `render_stream()` yields HTML chunks as template sections complete
4. Each chunk is sent to the client immediately via ASGI body messages
5. The browser renders each chunk as it arrives

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

## When to Use Streaming

Use `Stream` when:

- A page has multiple independent data sources with varying load times
- You want to show the page layout immediately
- Time-to-first-byte matters more than total render time
- You are building dashboards, feeds, or data-heavy pages

Use `Template` when:

- All data is available quickly
- The template is simple
- You need the complete response for caching or processing

## Next Steps

- [[docs/streaming/server-sent-events|Server-Sent Events]] -- Real-time push updates
- [[docs/core-concepts/return-values|Return Values]] -- All return types
- [[docs/templates/rendering|Rendering]] -- Standard template rendering
