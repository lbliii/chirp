---
title: No-Build High-State
description: Use Chirp islands and state primitives without bundlers
draft: false
weight: 35
lang: en
type: doc
tags: [guides, islands, state, no-build]
keywords: [islands, no-build, primitives, htmx, state]
category: guide
---

## Overview

Chirp lets you build stateful client widgets without React, Vite, or an npm
build step. Server-rendered HTML and [[docs/build-apps/html-fragments/fragments|htmx fragments]]
handle the data; small ES-module [[docs/build-apps/ui-extensions/islands|islands]]
— self-mounting widgets in `/static/islands/*.js` — handle client-only state
such as drag reorder, multi-step wizards, and optimistic toggles.

Reach for this when a widget needs richer client behavior than `hx-*` attributes
give you, but you do not want a front-end framework or its build pipeline. For
something lighter than an island, [[docs/build-apps/ui-extensions/alpine|Alpine.js]]
covers small interactivity inline in the template.

## Recommended stack

- Server rendering: Chirp + Kida templates
- Partial updates: htmx
- Stateful widgets: islands with `/static/islands/*.js` ES modules

## Reach for a primitive first

Chirp ships named primitives for the client-state shapes you hit most. Use one
of these before reaching for a full framework island:

`state_sync`, `action_queue`, `draft_store`, `error_boundary`, `grid_state`,
`wizard_state`, `upload_state`, `optimistic_apply`.

You mount a primitive with `primitive_attrs(...)`, which emits the
`data-island-primitive` metadata the runtime reads:

```html
<section{{ primitive_attrs("wizard_state", props={"stateKey": "signup", "steps": ["a", "b", "c"]}) }}>
  ...
</section>
```

## Optimistic UI without server state

`optimistic_apply` is the one primitive whose client runtime Chirp ships, so you
mount it without writing any JavaScript. It paints a mutation instantly from the
client's own snapshot, lets htmx do the real request, swaps the authoritative
server fragment on success, and reverts on failure. The server keeps **zero
per-client view state**: the handler is identical with or without the adapter.

```html
<button hx-post="/toggle-like" hx-target="#like-btn" hx-swap="outerHTML"
        {{ optimistic_attrs([{"op": "toggleClass", "value": "liked"},
                             {"op": "setText", "expr": "+1", "sel": ".count"},
                             {"op": "disable"}], mount_id="like-btn") }}>...</button>
```

:::{danger}
`optimistic_apply` holds **zero per-client view state on the server**. The op
vocabulary is a closed, reversible set (`addClass`, `removeClass`,
`toggleClass`, `setText`, `setAttr`, `removeAttr`, `disable`) — no raw HTML, so
there is no XSS surface to roll back. Any prop that would smuggle a
server-correlation key (`serverState`, `pendingId`, `optimisticId`, `clientId`,
`connectionId`, `mergeUrl`, `mergeEndpoint`) is **refused at render time**
(`optimistic_attrs(...)` raises `ValueError`) and flagged by `app.check()`. The
handler stays identical with or without the adapter; do not try to thread
per-client state through it.
:::

It closes ~80% of the optimistic-UI gap (one in-flight mutation per region,
last-write-wins, replacing swaps only). For concurrent collaborative editing,
reach for a framework island. Full op contract and guardrail:
[[docs/build-apps/ui-extensions/islands|Islands]].

## Decision rule

::::{tab-set}
::::{tab-item} Use no-build primitives
Choose a primitive when:

- state is local to one widget
- htmx still handles the server data boundaries
- you do not need a full client router or runtime
::::{/tab-item}
::::{tab-item} Use a framework island
Choose a framework island when:

- third-party JS libraries force framework lifecycle APIs
- component complexity becomes a mini-app with deep client-only state
::::{/tab-item}
::::{/tab-set}

For server-driven realtime (push from the server after the page loads), use
signals and SSE instead — see the [[docs/build-apps/streaming-updates/reactive-system|reactive system]].

:::{dropdown} Island mount checklist
Once you pick an island, wire these every time:

- include SSR fallback content in every mount root
- always set a stable mount `id`
- set `data-island-version` explicitly
- prefer `primitive_attrs(...)` over raw attributes to keep the props schema clear
- keep runtime diagnostics enabled — the runtime emits a `chirp:island:error`
  event you can listen for
:::{/dropdown}

:::{note} See also
- [[docs/build-apps/ui-extensions/islands|Islands]] — the full island runtime, mount contract, and `optimistic_apply` op vocabulary
- [[docs/build-apps/html-fragments/fragments|Fragments]] — the htmx swaps that carry your server data
- [[docs/build-apps/streaming-updates/reactive-system|Reactive system]] — signals and SSE for server-driven realtime
:::
