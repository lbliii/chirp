---
title: Alpine + htmx
description: Combine Alpine.js for local state with htmx for server round-trips
draft: false
weight: 25
lang: en
type: doc
tags: [tutorial, alpine, htmx, dropdown, modal]
keywords: [alpine, htmx, dropdown, modal, local-state]
category: tutorial
---

## Overview

Alpine.js handles state that lives entirely in the browser — a dropdown that's open or closed, a modal that's showing — without a server round-trip. htmx handles everything that needs the server: submitting a form, swapping in fresh HTML. This tutorial wires the two together so a dropdown or modal controls its own open/close while the form inside it posts to a route and swaps the result.

Reach for this combo when a UI element is interactive but its *data* still comes from the server. The two examples below are one pattern — Alpine owns the open/close, htmx owns the fetch — applied to a filter dropdown and a create-form modal.

## Setup

Turn on Alpine injection in your config. Chirp injects the Alpine script before `</body>` on every full-page HTML response, so your templates can use `x-data`, `x-show`, and `@click` anywhere:

```python
from chirp import App, AppConfig

config = AppConfig(alpine=True)
app = App(config=config)
```

The htmx attributes below (`hx-get`, `hx-post`) assume htmx is on the page. Either keep your own htmx `<script>` in the layout, or set `AppConfig(htmx=True)` to have Chirp inject it the same way it injects Alpine. Both flags default to off — Chirp never injects a script you didn't ask for. For the fragment-swap model these attributes drive, see [[docs/build-apps/html-fragments/fragments|fragments and swaps]].

:::{note}
On [[docs/build-apps/ui-extensions/chirp-ui|chirp-ui]], `use_chirp_ui(app)` sets `alpine=True` for you, so you skip the flag entirely. The full enable-it walkthrough lives in the [[docs/build-apps/ui-extensions/alpine|Alpine guide]].
:::

## Build it

Both examples below import a bundled macro, let Alpine own the open/close state, and let htmx fetch the HTML. Pick the variant you need.

:::{tab-set}
:::{tab-item} Dropdown filter

A filter dropdown that submits via htmx when an option is selected:

```html
{% from "chirp/alpine.html" import dropdown %}

{% call dropdown("Filter by status") %}
  <form hx-get="/tasks" hx-target="#task-list" hx-swap="innerHTML">
    <input type="hidden" name="status" value="open">
    <button type="submit" @click="open = false">Open</button>
  </form>
  <form hx-get="/tasks" hx-target="#task-list" hx-swap="innerHTML">
    <input type="hidden" name="status" value="closed">
    <button type="submit" @click="open = false">Closed</button>
  </form>
{% end %}

<div id="task-list">
  {% for task in tasks %}
    <div class="task">{{ task.title }}</div>
  {% endfor %}
</div>
```

The `dropdown` macro takes the trigger label as its first argument and ships its own `open` state. Alpine controls open/close; htmx runs the filter request and swaps `#task-list`.
:::{/tab-item}
:::{tab-item} Modal form

A "New task" button opens a modal; the form posts via htmx and closes the modal when the request completes. Pass `managed=false` so the parent's `open` state controls the modal:

```html
{% from "chirp/alpine.html" import modal %}

<div x-data="{ open: false }">
  <button type="button" @click="open = true">New Task</button>
  {% call modal("new-task-modal", title="New Task", managed=false) %}
    <form hx-post="/tasks" hx-target="#task-list" hx-swap="beforeend"
          @htmx:after-request="open = false">
      <input name="title" required>
      <button type="submit">Create</button>
    </form>
  {% end %}
</div>

<div id="task-list">
  {% for task in tasks %}
    <div class="task">{{ task.title }}</div>
  {% endfor %}
</div>
```

The parent `x-data` holds `open`. The button sets `open = true`; the form's `@htmx:after-request` sets `open = false` once the request finishes (it fires on any completed request, not only a 2xx). With `managed=false` the modal reads that parent `open` instead of declaring its own.
:::{/tab-item}
:::{/tab-set}

:::{tip} Prevent the modal flash
Add this once to your CSS so a modal stays hidden until Alpine initializes, instead of flashing fully open on first paint:

```css
[x-cloak] { display: none !important; }
```
:::

:::{warning}
A component inside an htmx-boosted region must register with `Alpine.safeData()`, not `Alpine.data()`, or it goes dead after a boosted navigation. The bundled `dropdown` and `modal` macros already do the right thing — this only bites custom components. See [[docs/build-apps/ui-extensions/alpine|registering custom components]] and [[docs/build-apps/ui-extensions/boosted-navigation|boosted navigation]] for the boost contract.
:::

:::{note} See also
- [[docs/build-apps/ui-extensions/alpine|Alpine guide]] — enable it, the macros, and registering your own components
- [[docs/tutorials/htmx-patterns|htmx patterns]] — more server-round-trip recipes
- [[docs/build-apps/ui-extensions/no-build-high-state|Single-page Alpine state]] — when the whole interaction lives in the browser
:::
