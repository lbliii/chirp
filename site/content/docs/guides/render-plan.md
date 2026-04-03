---
title: RenderPlan Middleware
description: Inspect rendering decisions from middleware for analytics, caching, and debugging
draft: false
weight: 55
lang: en
type: doc
tags: [middleware, render-plan, introspection, caching]
keywords: [render-plan, middleware, intent, layout, fragment, caching, analytics]
category: guide
---

## What Is a RenderPlan?

When a handler returns `Page`, `LayoutPage`, or `PageComposition`, Chirp's content negotiation layer builds a **RenderPlan** before producing HTML. The plan captures the rendering decision:

- **intent** -- `"full_page"`, `"page_fragment"`, or `"local_fragment"`
- **main_view** -- which template and block to render, with context
- **apply_layouts** -- whether to wrap content in the layout chain
- **layout_start_index** -- how deep into the layout chain to start
- **region_updates** -- OOB shell region swaps (breadcrumbs, sidebar, etc.)
- **response_headers** -- headers to set on the response

The plan is a frozen dataclass -- immutable and safe to inspect from middleware.

## Reading the Plan

After content negotiation runs, the frozen `RenderPlan` is stashed on the request. Read it with `get_render_plan()`:

```python
from chirp import get_render_plan

async def my_middleware(request, next):
    response = await next(request)
    plan = get_render_plan(request)
    if plan is not None:
        print(plan.intent)           # "full_page" or "page_fragment"
        print(plan.apply_layouts)    # True for full pages
        print(plan.layout_start_index)  # Layout chain depth
    return response
```

Returns `None` for non-page responses (strings, dicts, `Fragment`, `EventStream`, etc.).

## Practical Patterns

### Render Analytics

Track which rendering paths are hit most:

```python
from chirp import get_render_plan

async def analytics_middleware(request, next):
    response = await next(request)
    plan = get_render_plan(request)
    if plan is not None:
        metrics.increment(f"render.{plan.intent}")
        if plan.region_updates:
            metrics.increment("render.with_oob_regions")
    return response
```

### Plan-Aware Caching

Cache by render plan characteristics, not just URL:

```python
from chirp import get_render_plan

async def cache_middleware(request, next):
    plan_key = _cache_key(request)
    cached = cache.get(plan_key)
    if cached is not None:
        return cached

    response = await next(request)
    plan = get_render_plan(request)

    # Only cache full-page renders (fragments are user-specific)
    if plan is not None and plan.intent == "full_page":
        cache.set(plan_key, response, ttl=60)
    return response
```

### Debug Logging

Log rendering decisions in development:

```python
from chirp import get_render_plan

async def debug_middleware(request, next):
    response = await next(request)
    plan = get_render_plan(request)
    if plan is not None:
        logger.debug(
            "Rendered %s: intent=%s layouts=%s regions=%d",
            request.path,
            plan.intent,
            plan.apply_layouts,
            len(plan.region_updates),
        )
    return response
```

## RenderPlan Fields

| Field | Type | Description |
|-------|------|-------------|
| `intent` | `str` | `"full_page"`, `"page_fragment"`, or `"local_fragment"` |
| `main_view` | `ViewRef` | Template, block, and context for the main content |
| `render_full_template` | `bool` | True if rendering the entire template (not a block) |
| `apply_layouts` | `bool` | True if wrapping content in layout chain |
| `layout_chain` | `LayoutChain \| None` | The layout chain (for filesystem routing) |
| `layout_start_index` | `int` | Where to start in the layout chain |
| `layout_context` | `dict` | Context for layout rendering |
| `region_updates` | `tuple[RegionUpdate, ...]` | OOB shell region swaps |
| `include_layout_oob` | `bool` | Whether to include layout OOB blocks |
| `response_headers` | `dict[str, str]` | Extra response headers |

## Next Steps

- [[docs/core-concepts/return-values|Return Values]] -- How return types drive rendering decisions
- [[docs/middleware/custom|Custom Middleware]] -- Writing middleware in Chirp
