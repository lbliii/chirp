---
title: Hybrid static/dynamic freeze
description: Static HTML with live-block placeholders backed by an origin
draft: false
weight: 30
lang: en
type: doc
tags: [guides, freeze, live-blocks, hybrid, htmx]
keywords: [freeze, ssg, live-block, origin, placeholder]
category: guide
---

## Overview

`chirp freeze` normally renders every route to static HTML. **Live blocks** let
you keep 99 % of a page static while declaring named blocks that should render
dynamically at request time.

At freeze time the declared block's HTML is replaced with an htmx placeholder
pointing at the block-fetch dispatcher (`/_frag{path}?_b={block}`). The frozen
page deploys to any static host; the placeholder fetches the block from an
origin when the visitor loads the page.

## Declaring a live block

```python
from chirp import App, Fragment, Request

app = App()

@app.route("/docs/{slug:path}")
def docs(slug: str):
    return Page("docs/page.html", slug=slug)

@app.live_block(
    "/docs/{slug:path}",
    "recent_updates",
    trigger="load delay:100ms",
    skeleton="<div class='skel'>Loading…</div>",
)
async def recent_updates(request: Request) -> Fragment:
    slug = request.path_params["slug"]
    updates = await fetch_updates(slug)
    return Fragment("docs/page.html", "recent_updates", updates=updates)
```

Both arguments are validated at `app.check()`:

- `live_block_unreachable_route` — the route isn't registered.
- `live_block_unknown` — the template has no block with that name.

## Frozen output

After `chirp freeze`, the `recent_updates` block is emitted as:

```html
<div hx-get="/_frag/docs/intro?_b=recent_updates"
     hx-trigger="load delay:100ms"
     hx-swap="innerHTML"
     hx-target="this"
     data-chirp-live="recent_updates"><div class='skel'>Loading…</div></div>
```

Everything outside that block remains static — no JS is required to read the
rest of the page, and search engines index the surrounding content.

## What an origin must serve

The origin is any Chirp process mounted at the same URL space as the frozen
site. It handles exactly two concerns:

1. **`GET /_frag{path}?_b={block}`** — the block-fetch dispatcher. Registered
   automatically by Chirp; returns only the named block.
2. **Cache headers** — set `Cache-Control: public, s-maxage=…` on
   dispatcher responses you want your CDN to hold onto. Use `cache_seconds=`
   on the decorator to set the value from the declaration site.

If the origin is unreachable, the placeholder stays visible (htmx shows the
skeleton content). No JavaScript error is raised — the page still functions,
the live block just never resolves. This is the **graceful-degradation
guarantee**: frozen pages never become unusable because the origin is down.

## Deployment shapes

### Full hybrid (static + live origin)

- CDN / S3 / GitHub Pages serves `/dist` as usual.
- A small Chirp worker serves `/_frag/**` behind the CDN.
- Route `/_frag/*` requests to the worker via CDN path rules.

### Static-only (no origin)

- Just run `chirp freeze` without declaring any live blocks.
- Output is byte-identical to pre-live-blocks Chirp (**Invariant 1**).

### Origin-only (no freeze)

- Normal `chirp run` — every block resolves server-side.
- `@app.live_block` declarations are still valid; they just add no placeholders.

## Caveats

- Live blocks are matched against the rendered HTML by **string equality**.
  If the block renders to an empty string (no content), freeze emits a warning
  and skips rewriting that block.
- The leaf template's rendered context is used to render the block in
  isolation during freeze. Side-effectful template context (e.g. a generator
  that can only be iterated once) is not supported.
- The block-fetch URL scheme is reserved: user routes starting with `/_frag/`
  raise `ConfigurationError` at freeze time.
