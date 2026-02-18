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
- `data-island-src` (optional): adapter/runtime hint for lazy loaders.
- `id` (recommended): stable mount id for deterministic remount targeting.

## Props Rules

- Props must be JSON-serializable (`dict`, `list`, string, number, bool, null).
- Chirp helper APIs serialize and escape props for HTML attributes.
- Avoid hand-writing JSON in templates; use helpers:
  - `{{ state | island_props }}`
  - `{{ island_attrs("editor", props=state, mount_id="editor-root") }}`

## Lifecycle Events

When `AppConfig(islands=True)` is enabled, Chirp injects a small runtime that:

- scans for `[data-island]` on page load
- unmounts islands before htmx swaps
- mounts/remounts islands after htmx swaps

Browser events emitted:

- `chirp:island:mount`
- `chirp:island:unmount`
- `chirp:island:remount`
- `chirp:islands:ready`

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

`app.check()` / `chirp check` validate islands metadata:

- malformed `data-island-props` JSON -> error
- optional strict mode warning when island roots omit `id`

## Graceful Degradation

Always place useful fallback markup inside the mount root. If island runtime
fails, the SSR fallback remains visible and functional.

## Non-goals (V1)

- no built-in framework adapter (React/Svelte/Vue are user-land)
- no global hydration framework
- no client router replacement
