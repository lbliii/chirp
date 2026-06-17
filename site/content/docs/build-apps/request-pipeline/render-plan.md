---
title: RenderPlan Middleware
description: Inspect rendering decisions from middleware for analytics, caching, and debugging
draft: false
weight: 40
lang: en
type: doc
tags: [middleware, render-plan, introspection, caching]
keywords: [render-plan, middleware, intent, layout, fragment, caching, analytics]
category: guide
---

## What Is a RenderPlan?

A **RenderPlan** is Chirp's record of how it decided to render a request: full page vs. fragment, which template block, whether to wrap it in a layout, and which OOB regions to swap. Chirp builds this plan internally for every page response, then stashes it on the request so your middleware can read it after the fact.

Reach for it when you want to act on the rendering decision -- log it, collect metrics on it, or cache by it -- without re-deriving how the request was served. The fields you usually touch are:

- **intent** -- `"full_page"`, `"page_fragment"`, or `"local_fragment"`
- **apply_layouts** -- whether content was wrapped in the [[docs/build-apps/html-fragments/layout-patterns|layout chain]]
- **region_updates** -- [[docs/quality/contracts-debugging/oob-registry|OOB shell region swaps]] (breadcrumbs, sidebar, etc.)
- **layout_start_index** -- how deep into the layout chain rendering started

:::{note} When is a plan built?
A plan is built whenever a page handler returns a `Page` -- or one of Chirp's internal page types, `LayoutPage` / `PageComposition`, which you read but never construct directly. The decision is driven by [[docs/about/core-concepts/return-values|content negotiation]] on the return type. `get_render_plan()` returns `None` for everything else (strings, dicts, `Fragment`, `EventStream`).
:::

## Reading the Plan

After content negotiation runs, the `RenderPlan` is stashed on the request. Read it with `get_render_plan()`:

```python
from chirp import AnyResponse, Next, Request, get_render_plan

async def my_middleware(request: Request, next: Next) -> AnyResponse:
    response = await next(request)
    plan = get_render_plan(request)
    if plan is not None:
        print(plan.intent)           # "full_page" or "page_fragment"
        print(plan.apply_layouts)    # True for full pages
        print(plan.layout_start_index)  # Layout chain depth
    return response
```

Returns `None` for non-page responses (strings, dicts, `Fragment`, `EventStream`, etc.).

:::{tip} Safe to call from any middleware
The plan is a frozen, immutable object. Inspecting it -- from analytics, caching, or logging middleware -- can never change what the user sees, so there's no need to copy or guard it.
:::

## Practical Patterns

### Render Analytics

Track which rendering paths are hit most:

```python
from chirp import get_render_plan

async def analytics_middleware(request: Request, next: Next) -> AnyResponse:
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

async def cache_middleware(request: Request, next: Next) -> AnyResponse:
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

async def debug_middleware(request: Request, next: Next) -> AnyResponse:
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

:::{dropdown} Full field reference
Most middleware only reads `intent`, `apply_layouts`, `region_updates`, and `layout_start_index` (all shown in the examples above). The complete frozen `RenderPlan` looks like this. Types marked *(read-only)* are Chirp's internal types -- you inspect them, you never construct them.

| Field | Type | Description |
|-------|------|-------------|
| `intent` | `str` | `"full_page"`, `"page_fragment"`, or `"local_fragment"` |
| `main_view` | `ViewRef` *(read-only)* | Template, block, and context for the main content |
| `render_full_template` | `bool` | True if rendering the entire template (not a block) |
| `apply_layouts` | `bool` | True if wrapping content in the layout chain |
| `layout_chain` | `LayoutChain \| None` *(read-only)* | The layout chain (for filesystem routing) |
| `layout_start_index` | `int` | Where to start in the layout chain |
| `layout_context` | `dict` | Context for layout rendering |
| `region_updates` | `tuple[RegionUpdate, ...]` *(read-only)* | OOB shell region swaps |
| `include_layout_oob` | `bool` | Whether to include layout OOB blocks |
| `response_headers` | `dict[str, str]` | Extra response headers |
:::{/dropdown}

:::{note} See also

- [[docs/about/core-concepts/return-values|Return Values]] -- how return types drive rendering decisions
- [[docs/build-apps/request-pipeline/custom|Custom Middleware]] -- writing middleware in Chirp
- [[docs/build-apps/html-fragments/layout-patterns|Layout Patterns]] -- the layout chain a plan wraps content in
:::
