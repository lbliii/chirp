---
title: Islands Contract (V1)
description: Framework-agnostic contract for isolated high-state UI islands
draft: false
weight: 30
lang: en
type: doc
tags: [guides, islands, htmx, progressive-enhancement]
keywords: [islands, data-island, hydration, remount, fallback]
category: guide
---

## Overview

Chirp islands let you keep the app server-rendered by default while mounting
isolated high-state widgets where needed (editors, canvases, complex grids).
The contract is framework-agnostic: React/Svelte/Vue adapters can all target
the same mount metadata and lifecycle events.

Chirp also supports a no-build primitive style, where islands load plain ES
modules served from static assets (`/static/islands/*.js`).

## Mount Root Contract

An island mount root is any element with `data-island`:

```html
<div
  id="editor-root"
  data-island="editor"
  data-island-version="1"
  data-island-src="/static/editor.js"
  data-island-props="{&quot;doc_id&quot;:42,&quot;mode&quot;:&quot;advanced&quot;}"
>
  <p>Fallback editor UI for no-JS mode.</p>
</div>
```

Supported attributes:

- `data-island` (required): logical island name used by your client adapter.
- `data-island-version` (recommended): contract/runtime version (default `"1"`).
- `data-island-props` (optional): JSON payload for initial state.
- `data-island-src` (optional): adapter/runtime hint for lazy loaders (never use `javascript:`).
- `id` (recommended): stable mount id for deterministic remount targeting.
- `data-island-primitive` (optional): explicit primitive type tag for contract checks.

## Props Rules

- Props must be JSON-serializable (`dict`, `list`, string, number, boolean, null).
- Chirp helpers serialize and escape props for HTML attributes.
- Avoid hand-writing JSON in templates; use helpers:
  - `{{ state | island_props }}`
  - `{{ island_attrs("editor", props=state, mount_id="editor-root") }}`

## Lifecycle Events

With `AppConfig(islands=True)`, Chirp injects a small runtime that:

- scans for `[data-island]` on page load
- unmounts islands before htmx swaps
- mounts/remounts islands after htmx swaps

Browser events emitted:

- `chirp:island:mount`
- `chirp:island:unmount`
- `chirp:island:remount`
- `chirp:island:error`
- `chirp:islands:ready`
- `chirp:island:state` (state channel)
- `chirp:island:action` (action channel)

Each event `detail` includes:

- `name`, `id`, `version`, `src`, `props`, `element`

## Runtime Configuration

```python
from chirp import App, AppConfig

app = App(
    AppConfig(
        islands=True,
        islands_version="1",
        islands_contract_strict=True,  # optional checks in app.check()
    )
)
```

## Validation

`app.check()` / `chirp check` check islands metadata:

- malformed `data-island-props` JSON -> error
- invalid `data-island-version` format -> error
- unsafe `data-island-src` (`javascript:`) -> error
- optional strict mode warning when island roots omit `id`
- optional strict mode warning when templates omit `data-island-version`
- primitive schema checks for known no-build primitives

Known primitive contracts:

- `state_sync` -> `stateKey`
- `action_queue` -> `actionId`
- `draft_store` -> `draftKey`
- `grid_state` -> `stateKey`, `columns`
- `wizard_state` -> `stateKey`, `steps`
- `upload_state` -> `stateKey`, `endpoint`

## Diagnostics

The runtime emits `chirp:island:error` for mount-level issues:

- malformed `data-island-props` (runtime parse failure)
- unsafe `data-island-src`
- mount/runtime version mismatch (warning-level event)

The runtime also exposes a small channel API:

- `window.chirpIslands.register(name, adapter)`
- `window.chirpIslands.emitState(payload, state)`
- `window.chirpIslands.emitAction(payload, action, status, extra)`
- `window.chirpIslands.channels` (`state`, `action`, `error`)

## Graceful Degradation

Always place useful fallback markup inside the mount root. If island runtime
fails, the SSR fallback remains visible and functional.

## Non-goals (V1)

- no built-in framework adapter (React/Svelte/Vue are user-land)
- no global hydration framework
- no client router replacement
