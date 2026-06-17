---
title: Hybrid Static/Dynamic Freeze
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

:::{since} 0.5.0
Live blocks and hybrid freeze shipped in 0.5.0.
:::

`chirp freeze` renders your whole app to static HTML you can deploy to any CDN
or static host — no running server required. But some content can't be frozen:
a "recent updates" panel, a live count, anything that changes between deploys.

**Live blocks** let you keep a page static while marking individual
[[docs/build-apps/html-fragments/fragment-blocks|template blocks]] to render
dynamically at request time. The frozen page ships everywhere; each live block
fetches itself from a small *origin* process — any running Chirp worker — when
a visitor loads the page.

If the origin is down, the rest of the page still works. The skeleton stays
visible, no JavaScript error is raised, and search engines still index the
static content. That graceful-degradation guarantee is the reason to reach for
hybrid freeze instead of going fully dynamic.

## Declaring a live block

You declare a live block with `@app.live_block`, pointing it at a registered
route and a named block in that route's template. The decorator marks the block
for freeze-time rewriting and validation — it does **not** add a separate
data-fetch hook. At request time the block-fetch dispatcher invokes the
**route's own handler** and extracts the named block from whatever
[[docs/build-apps/html-fragments/fragments|Fragment]] or
[[docs/about/core-concepts/return-values|return value]] it produces. So the data
the live block needs comes from the route handler's context, the same context
the full page renders from.

```python
from chirp import App, Page

app = App()

@app.route("/docs/{slug:path}")
async def docs(slug: str):
    # The route handler supplies the context for every block, live or static.
    return Page("docs/page.html", slug=slug, updates=await fetch_updates(slug))

@app.live_block(
    "/docs/{slug:path}",
    "recent_updates",
    trigger="load delay:100ms",
    skeleton="<div class='skel'>Loading…</div>",
)
def recent_updates():
    """Marks `recent_updates` as live. Never invoked — see the note below."""
```

Both arguments are validated at [[docs/quality/contracts-debugging/categories|`app.check()`]]:

- `live_block_unreachable_route` — the route isn't registered.
- `live_block_unknown` — the template has no block with that name.

:::{warning}
The function you decorate with `@app.live_block` is never called at request
time. The block-fetch dispatcher runs the **route handler** and re-renders the
named block from its context — it does not look up the decorated function. Put
the data the live block needs in the route handler's context (as `updates=`
above); a `fetch` placed in the decorated function's body will never run.
:::

## What an origin must serve

The origin is any Chirp process mounted at the same URL space as the frozen
site. It handles exactly one concern: **`GET /_frag{path}?_b={block}`**, the
block-fetch dispatcher. Chirp registers this route automatically; it matches the
underlying route for `{path}`, invokes its handler, and returns only the named
block.

To let your CDN hold onto dispatcher responses, set `Cache-Control: public,
s-maxage=…` on them at the CDN or origin layer.

If the origin is unreachable, the placeholder stays visible — htmx shows the
skeleton content. No JavaScript error is raised, the page still functions, and
the live block just never resolves. This is the **graceful-degradation
guarantee**: frozen pages never become unusable because the origin is down.

:::{dropdown} What the frozen placeholder looks like
After `chirp freeze`, the `recent_updates` block is emitted as:

```html
<div hx-get="/_frag/docs/intro?_b=recent_updates"
     hx-trigger="load delay:100ms"
     hx-swap="innerHTML"
     hx-target="this"
     data-chirp-live="recent_updates"><div class='skel'>Loading…</div></div>
```

Everything outside that block stays static — no JS is required to read the
rest of the page, and search engines index the surrounding content. You rarely
hand-edit this output; the dispatcher and your `skeleton=` argument produce it.
:::

## Deployment shapes

Pick the shape that matches whether you freeze, run live, or both.

::::{steps}
:::{step} Full hybrid (static + live origin)
- CDN / S3 / GitHub Pages serves `/dist` as usual.
- A small Chirp worker serves `/_frag/**` behind the CDN.
- Route `/_frag/*` requests to the worker via CDN path rules.
:::{/step}
:::{step} Static-only (no origin)
- Run `chirp freeze` without declaring any live blocks.
- A pure-static freeze with no live blocks produces byte-identical output to
  pre-live-blocks Chirp.
:::{/step}
:::{step} Origin-only (no freeze)
- Normal `chirp run` — every block resolves server-side.
- `@app.live_block` declarations are still valid; they just add no placeholders.
:::{/step}
::::{/steps}

## Caveats

:::{warning}
Two declarations fail the freeze if you get them wrong:

- **The `/_frag/` prefix is reserved.** A user route starting with `/_frag/`
  raises `ConfigurationError` at freeze time — the block-fetch dispatcher owns
  that namespace.
- **`freeze_params` values must be normal path segments.** Values that
  introduce `.` or `..` segments are reported as freeze errors and never
  written to disk.
:::

:::{note}
Live blocks are matched against the rendered HTML by **string equality**. If a
block renders to an empty string, freeze records an error and skips rewriting
that block. The leaf template's rendered context is reused to render the block
in isolation during freeze, so side-effectful context (e.g. a generator that
can only be iterated once) is not supported.
:::

:::{note} See also
- [[docs/quality/deployment/production|Production deployment]] — the rest of the deploy checklist.
- [[docs/quality/deployment/_index|The freeze deployment section]] — sibling deploy guides.
:::
