---
title: htmx
description: Chirp-managed htmx injection — the hypermedia transport for hx-* attributes, swaps, and boosts
draft: false
weight: 21
lang: en
type: doc
tags: [guides, htmx, hypermedia, swaps, sse]
keywords: [htmx, hx-get, hx-post, swap, boost, sse, provisioning]
category: guide
---

## Overview

htmx is the core hypermedia transport: it powers `hx-get`/`hx-post` requests,
partial swaps, `hx-boost` navigation, and (with the SSE extension) `sse-connect`
streams. None of those attributes do anything unless the htmx runtime is loaded
on the page.

Chirp can be the **single authority** for htmx. When `AppConfig(htmx=True)`, the
`HtmxInject` middleware appends the htmx `<script>` before `</body>` on every
full-page response — so you write `hx-*` attributes in your templates and never
hand-roll a `<script src="...htmx...">` tag. This mirrors how `AppConfig(alpine=True)`
manages Alpine.

## When to Use htmx vs Alpine

| Use htmx for | Use Alpine for |
|--------------|----------------|
| Form submissions, partial swaps | Dropdowns, modals, tabs |
| Search-as-you-type | Toggles, accordions |
| SSE live updates | Local validation before submit |
| Server-driven content | Client-only state |

## Enabling htmx

Enable htmx injection explicitly in your config:

```python
from chirp import App, AppConfig

config = AppConfig(htmx=True)
app = App(config=config)
```

Chirp is the **single authority** for htmx injection. `HtmxInject` appends the script **before the first `</body>`** on:

- **Buffered HTML responses** — full pages and eligible buffered bodies (subject to the same fragment / render-intent gating as `AlpineInject`).
- **Streaming HTML** — `StreamingResponse` bodies (for example `Suspense`, `Stream`, `TemplateStream`) are rewritten chunk-by-chunk so htmx appears in the final document without buffering the entire stream in memory.

Fragment responses (htmx partials) and other non-HTML responses are unchanged. If htmx is already present before `</body>` (detected via `data-chirp="htmx"`), injection is skipped to prevent double-loading.

The injection block includes:

- **htmx core** (unpkg CDN, the IIFE browser build that defines `window.htmx`)
- **htmx SSE extension** (`htmx-ext-sse`) — only when `htmx_sse=True`

The opt-in defaults to off, so apps that hand-provision htmx (such as the
generated chirpui scaffold, which ships its own `<script>` tags) are unaffected.

## CDN URL: unpkg, not a bare jsDelivr npm path

Chirp injects htmx from **unpkg** (`https://unpkg.com/htmx.org@{htmx_version}`).
unpkg's `htmx.org@VER` *is* the browser IIFE build that defines the global
`window.htmx`, so no `/dist/...` subpath is required.

Do **not** swap this to a bare jsDelivr npm path like
`https://cdn.jsdelivr.net/npm/htmx.org@2.0.4` — jsDelivr resolves a bare npm
specifier to the package's CommonJS `main`, which throws `ReferenceError: module
is not defined` in the browser. The failure is silent (CORS masks the cross-origin
script error as a bare `"Script error."`), so every `hx-*` attribute on the page
goes dead with no console trace. This is the same class of footgun as the Alpine
CDN path, with the inverse resolution: Alpine *needs* the explicit
`/dist/cdn.min.js`, htmx *needs* the bare unpkg path.

## htmx SSE extension (`htmx_sse`)

To wire SSE streams (`sse-connect`, `sse-swap`) with htmx, you need the htmx SSE
extension in addition to the core runtime. Set `htmx_sse=True` and Chirp injects
both:

```python
config = AppConfig(htmx=True, htmx_sse=True)
```

The SSE extension is pinned to a version that matches the chirpui scaffold
(`htmx-ext-sse@2.2.2/sse.js`) and carries its own `data-chirp="htmx-sse"` marker.

## The `data-chirp="htmx"` dedup marker

The injected htmx core `<script>` carries `data-chirp="htmx"`. Before injecting,
`HtmxInject` scans the document for that marker preceding the first `</body>`; if
it is already present, injection is skipped. This is what makes the opt-in safe:

- An app that sets `htmx=True` *and* ships its own htmx `<script>` is not
  double-loaded — but only if that hand-written tag also carries the marker, so
  the framework's own injected tags (and the chirpui scaffold's tags) include it.
- Hand-rolled vendor tags without the marker will be deduped only if their `src`
  is otherwise detected; the reliable contract is: let Chirp inject (Mode A) *or*
  ship your own `<script>` (Mode B), not both.

## The htmx provisioning contract

`app.check()` includes an `htmx_provisioning` rule. A template that emits htmx
attributes (`hx-get`, `hx-post`, `hx-trigger`, `hx-boost`, `hx-ext`,
`sse-connect`, `sse-swap`, …) but ships no htmx runtime renders a UI whose
buttons, forms, and streams silently do nothing. The rule raises an **ERROR**
unless htmx is provisioned one of two ways:

- **Mode A — `AppConfig(htmx=True)`**: Chirp's `HtmxInject` provisions every
  full-page response, so the whole app is covered regardless of templates.
- **Mode B — an explicit htmx `<script src="...htmx...">`** reachable from the
  page (its own template, the layout it extends, or — for filesystem-routing
  pages — the layout chain and its `extends`/`include` closure). A single
  matching script anywhere in that reachable closure provisions the whole
  composed page.

The usage scan skips framework-shipped templates (`chirp/`, `chirpui/`,
`chirp_docs/`) — provisioning those is the host app's responsibility, not the
framework's. If you self-host htmx under a filename the `src`-contains-`htmx`
heuristic cannot see (a custom bundle, `/static/vendor.js`, an npm import), set
`AppConfig(htmx=True)` as the explicit opt-in so the check passes.

## Configuration Options

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `htmx` | `bool` | `False` | Enable Chirp-managed htmx script injection (Mode A provisioning) |
| `htmx_version` | `str` | `"2.0.4"` | Pinned htmx core version (unpkg CDN) |
| `htmx_sse` | `bool` | `False` | Also inject the htmx SSE extension (`htmx-ext-sse`) |

## htmx + Alpine Together

htmx and Alpine compose cleanly: htmx owns the server round-trips, Alpine owns
local UI state. Enable both:

```python
config = AppConfig(htmx=True, alpine=True)
```

See the [Alpine + htmx tutorial](/chirp/docs/tutorials/alpine-htmx/) for a
worked example (a dropdown that submits via htmx, a modal whose form swaps a
list). For named Alpine components that must survive htmx boosted navigation,
register them with `Alpine.safeData()` (see the [Alpine guide](/chirp/docs/build-apps/ui-extensions/alpine/#registering-custom-components-alpinesafedata)).
