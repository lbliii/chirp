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

```python
from chirp import App, AppConfig

config = AppConfig(alpine=True)
app = App(config=config)
```

The Alpine script is injected into full-page HTML responses only. Fragment responses (htmx partials) are unchanged.

## Configuration Options

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `alpine` | `bool` | `False` | Enable Alpine.js script injection |
| `alpine_version` | `str` | `"3.15.8"` | Pinned Alpine version (unpkg CDN) |
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
