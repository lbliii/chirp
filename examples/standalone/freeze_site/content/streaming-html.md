---
title: Streaming HTML with Suspense
order: 2
category: Articles
description: Instant shells with deferred content blocks.
tags: [chirp, streaming, sse]
---

# Streaming HTML with Suspense

Chirp's `Suspense` return type renders a shell immediately, then streams
deferred blocks as they resolve. The user sees instant structure with content
filling in.

## How It Works

```python
return Suspense("dashboard.html",
    title="Dashboard",       # sync — in the shell
    stats=load_stats(),      # awaitable — deferred
    feed=load_feed(),        # awaitable — deferred
)
```

The shell renders with `stats` and `feed` set to `None`. Template blocks that
depend on these values show skeleton content. Then each block re-renders and
streams as an out-of-band swap.

## Why This Matters

- **First paint is instant** — the layout, nav, and static content render
  immediately
- **No loading spinners** — skeleton content is in the initial HTML, not
  injected by JavaScript
- **Progressive** — if the connection drops, the user still has the shell
- **No client framework** — OOB swaps are native htmx
