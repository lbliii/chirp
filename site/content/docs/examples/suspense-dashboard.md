---
title: Suspense Dashboard
description: Shell-first initial render with deferred blocks and OOB swaps
draft: false
weight: 40
lang: en
type: doc
tags: [examples, suspense, streaming, oob]
keywords: [suspense, dashboard, deferred, stream, oob]
category: examples
---

## What you get

This example builds a sales dashboard whose shell paints instantly while three
slow data sources — revenue, visitors, and recent orders — fill in afterward.
It all happens in a single HTTP response, with no extra client requests and no
JavaScript framework.

Copy this example when a page has several independent slow queries and you want
an instant first paint instead of one spinner blocking the whole page. The
return type that does the work is [[docs/about/core-concepts/return-values|`Suspense`]].

## The handler

The whole feature is one return type. Each awaitable in the context is deferred:
the shell renders first, then each value streams back as it resolves.

```python
from chirp import App, AppConfig, Suspense

config = AppConfig(template_dir=TEMPLATES_DIR, worker_mode="async")
app = App(config=config)


@app.route("/")
def dashboard():
    """Shell renders instantly, data blocks fill in as they resolve."""
    return Suspense(
        "dashboard.html",
        title="Sales Dashboard",     # sync — in the shell
        revenue=load_revenue(),      # awaitable — deferred
        orders=load_orders(),        # awaitable — deferred
        visitors=load_visitors(),    # awaitable — deferred
    )
```

*Source: [`examples/standalone/suspense_dashboard/app.py`](https://github.com/lbliii/chirp/blob/main/examples/standalone/suspense_dashboard/app.py).*

In the template, branch on `is deferred` to show a skeleton until the value
arrives, then render the loaded state:

```html
{% block revenue %}
  {% if revenue is deferred %}
    <div class="skeleton">Loading revenue…</div>
  {% else %}
    <p>{{ revenue.total }} ({{ revenue.period }})</p>
  {% endif %}
{% endblock %}
```

Each resolved block streams back as an [[docs/build-apps/html-fragments/fragment-blocks|OOB swap]]
that replaces its skeleton in place.

When those loaders hit PostgreSQL through Chirp's `Database` / Pelt pool, each
independent defer checks out its **own** connection for that await. If more
defers need a connection than `pool_size` allows, excess acquires wait until a
sibling releases — size the pool to peak concurrent independent checkouts, or
accept queueing. Do not hold one checkout across unrelated awaits between
defers.

:::{tip} Suspense vs. an event stream
Reach for `Suspense` when slow data should fill an *initial* render in one round
trip — the shell paints, then deferred blocks arrive on the same response. For
updates that arrive *after* the page is loaded (notifications, a live ticker),
use [[docs/build-apps/streaming-updates/server-sent-events|post-load SSE]] with
`EventStream` instead.
:::

## Run it

```bash
PYTHONPATH=src python examples/standalone/suspense_dashboard/app.py
```

Open `http://127.0.0.1:8000/`.

## Test it

```bash
pytest examples/standalone/suspense_dashboard/
```

:::{dropdown} Why test `is deferred`, not the value itself
A deferred key is the `DEFERRED` sentinel in the shell render, then resolves to
real data. Branching on bare truthiness (`{% if revenue %}`) treats an empty
list, `0`, `""`, and `False` as identical to the loading state — so the skeleton
can render forever and the user sees a perpetual spinner with no console error.

Always test `is deferred` (or membership in `__chirp_defer_pending__`) to
separate loading from loaded *before* you test the resolved value. `chirp check`
promotes this to a startup contract: it emits a `defer_falsy` WARNING when a
template self-declares a deferred key and then branches on its bare truthiness.

This example does not need `defer_blocks` — every deferred block is discovered
automatically. Pass `defer_blocks` only when static discovery misses a block
(for example, a deferred value handed through a macro argument).
:::

:::{related}
:::
