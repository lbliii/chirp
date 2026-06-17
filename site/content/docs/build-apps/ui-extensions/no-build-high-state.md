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

## Why this guide

You can keep Chirp server-first and still handle complex client state. The
default path does not require React, Vite, or npm build pipelines.

## Recommended stack

- Server rendering: Chirp + Kida templates
- Partial updates: htmx
- Stateful widgets: islands with `/static/islands/*.js` ES modules

## Primitive-first pattern

Use known primitives first (`state_sync`, `action_queue`, `draft_store`,
`error_boundary`, `grid_state`, `wizard_state`, `upload_state`,
`optimistic_apply`) before reaching for a full framework island.

```html
<section{{ primitive_attrs("wizard_state", props={"stateKey": "signup", "steps": ["a", "b", "c"]}) }}>
  ...
</section>
```

## Optimistic UI without server state

`optimistic_apply` is the one **blessed** primitive — Chirp ships its runtime, so
it Just Works. It paints a mutation instantly from the client's own snapshot,
lets htmx do the real request, swaps the authoritative server fragment on
success, and reverts on failure. The server keeps **zero per-client view
state**: the handler is identical with or without the adapter.

```html
<button hx-post="/toggle-like" hx-target="#like-btn" hx-swap="outerHTML"
        {{ optimistic_attrs([{"op": "toggleClass", "value": "liked"},
                             {"op": "setText", "expr": "+1", "sel": ".count"},
                             {"op": "disable"}], mount_id="like-btn") }}>...</button>
```

It closes ~80% of the optimistic-UI gap (one in-flight mutation per region,
last-write-wins, replacing swaps only). For concurrent collaborative editing,
reach for a framework island. Full contract: see
[Islands](/chirp/docs/build-apps/ui-extensions/islands/).

## Decision rule

Choose no-build primitives when:

- state is local to one widget
- htmx still handles server data boundaries
- you do not need a full client router/runtime

Choose framework islands when:

- third-party JS libraries force framework lifecycle APIs
- component complexity becomes a mini-app with deep client-only state

## Operational checklist

- include SSR fallback content in every mount root
- always set stable mount `id`
- set `data-island-version` explicitly
- prefer `primitive_attrs(...)` to keep props schema clear
- keep runtime diagnostics enabled (`chirp:island:error`)
