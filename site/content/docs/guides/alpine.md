---
title: Alpine.js
description: Local UI state with Alpine.js — dropdowns, modals, tabs
draft: false
weight: 20
lang: en
type: doc
tags: [guides, alpine, htmx, client-state]
keywords: [alpine, dropdown, modal, tabs, local-state]
category: guide
---

## Overview

Alpine.js complements htmx for **client-only UI state**: dropdowns, modals, tabs, accordions. htmx handles server round-trips; Alpine handles interactions that don't need a request.

Chirp integrates Alpine via config and macros. When enabled, the Alpine script is auto-injected before `</body>`.

## When to Use Alpine vs htmx

| Use Alpine for | Use htmx for |
|----------------|--------------|
| Dropdowns, modals, tabs | Form submissions, partial swaps |
| Toggles, accordions | Search-as-you-type |
| Local validation before submit | SSE live updates |
| Client-only state | Server-driven content |

## Enabling Alpine

If you use `chirp-ui`, Alpine is enabled automatically:

```python
from chirp import App, use_chirp_ui

app = App()
use_chirp_ui(app)  # auto-enables alpine=True
```

For apps without `chirp-ui`, enable it explicitly:

```python
from chirp import App, AppConfig

config = AppConfig(alpine=True)
app = App(config=config)
```

Chirp is the **single authority** for Alpine.js injection. The script is injected into full-page HTML responses only. Fragment responses (htmx partials) are unchanged. If Alpine is already present in the response (e.g. from a third-party layout), Chirp's `AlpineInject` middleware skips injection to prevent double-loading.

The injection block includes:

- **Alpine core** (jsdelivr CDN)
- **Plugins**: Mask, Intersect, Focus
- **Store init**: `modals` and `trays` stores for chirp-ui components
- **`Alpine.safeData()` helper** for htmx-safe component registration

## Configuration Options

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `alpine` | `bool` | `False` | Enable Alpine.js script injection (`use_chirp_ui` sets this to `True` automatically) |
| `alpine_version` | `str` | `"3.15.8"` | Pinned Alpine version (jsdelivr CDN) |
| `alpine_csp` | `bool` | `False` | Use CSP-safe build for strict Content-Security-Policy |

For strict CSP, set `alpine_csp=True` and ensure your CSP allows the Alpine script.

## Using the Macros

Import Chirp's Alpine macros and use them in your templates:

```html
{% from "chirp/alpine.html" import dropdown, modal, tabs %}

{% call dropdown("Menu") %}
  <a href="/a">Link A</a>
  <a href="/b">Link B</a>
{% end %}

{% call modal("confirm-dialog", title="Confirm") %}
  <p>Are you sure?</p>
  <button @click="open = false">Yes</button>
  <button @click="open = false">Cancel</button>
{% end %}

{% call tabs(["Overview", "Details"], "Overview") %}
  <div x-show="active === 'Overview'">Overview content</div>
  <div x-show="active === 'Details'">Details content</div>
{% end %}
```

### Dropdown

- `dropdown(trigger, wrapper_class="", panel_class="")` — Toggle panel with click-outside and Escape key
- Accessible: `aria-expanded`, `aria-haspopup`, `role="menu"`

### Modal

- `modal(id, title="", wrapper_class="", content_class="", managed=true)` — Dialog with Escape to close
- `managed=true` (default): self-contained. `managed=false`: use parent's `open` variable so a sibling button can control it
- Add `[x-cloak]{display:none!important}` to your CSS so the modal stays hidden until Alpine initializes
- Accessible: `role="dialog"`, `aria-modal`, `aria-hidden`

### Tabs

- `tabs(tab_names, default=none, tab_list_class="", panel_class="")` — Tab list + panel slot
- Caller provides panel content with `x-show="active === 'TabName'"` per panel

## Registering Custom Components (`Alpine.safeData`)

When you register named Alpine components with `Alpine.data()`, the standard `alpine:init` event only fires once on the initial page load. Under htmx boosted navigation, swapped-in scripts that rely on `alpine:init` will not re-register.

Chirp provides `Alpine.safeData(name, factory)` — a drop-in replacement for `Alpine.data()` that works on both initial loads and htmx-boosted navigations:

```html
<script>
Alpine.safeData("counter", () => ({
  count: 0,
  increment() { this.count++; },
}));
</script>

<div x-data="counter">
  <span x-text="count"></span>
  <button @click="increment">+</button>
</div>
```

**Why not `Alpine.data()` directly?** On the first page load, `Alpine.data()` must be called during or before the `alpine:init` event — but after Alpine is loaded. On subsequent htmx navigations, Alpine is already initialized so `Alpine.data()` works immediately. `Alpine.safeData()` handles both cases: it queues registrations until Alpine is ready, then becomes a direct passthrough.

## htmx + Alpine Together

Alpine 3 uses a mutation observer to discover new elements. When htmx swaps in HTML that contains Alpine attributes (`x-data`, `x-show`), Alpine initializes them automatically. No extra wiring needed.

Example: a dropdown inside an htmx-swapped fragment:

```html
<div id="user-card" hx-get="/users/1" hx-trigger="load" hx-swap="innerHTML">
  Loading...
</div>
```

The server returns:

```html
{% from "chirp/alpine.html" import dropdown %}
{% call dropdown("Actions") %}
  <a href="/users/1/edit">Edit</a>
  <button hx-delete="/users/1" hx-target="#user-card">Delete</button>
{% end %}
```

Alpine initializes the dropdown when the fragment is swapped in.

## CSP Setup

For strict Content-Security-Policy:

1. Set `AppConfig(alpine_csp=True)`
2. Ensure your CSP allows the Alpine script source (e.g. `https://unpkg.com`)
3. If using `eval()`-based policies, Alpine's CSP build avoids `eval`
