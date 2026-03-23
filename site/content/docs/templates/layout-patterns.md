---
title: Layout Patterns
description: Block-heavy layouts, boost pattern, and composition
draft: false
weight: 25
lang: en
type: doc
tags: [templates, blocks, layout, boost, composition]
keywords: [blocks, extends, include, call, layout, boost]
category: guide
---

## Overview

Chirp templates use Kida's block system: `{% extends %}`, `{% block %}`, `{% include %}`, and `{% call %}`. This guide covers patterns for block-heavy layouts and when to use each construct.

## Choosing a Layout

Pick the right base layout before writing any templates.

For **fixed column ratios** on page content (`grid()` + `block(span=…)`), see the Chirp UI package **`docs/LAYOUT-OVERFLOW.md`** (section *Fixed columns: grid presets*).

| Scenario | Layout |
|---|---|
| App shell with sidebar navigation | `chirpui/app_shell_layout.html` |
| htmx-boosted multi-page app | `chirp/layouts/boost.html` |
| Fragment-only app (LLM, RAG, forms only) | `chirp/layouts/shell.html` |
| Custom layout from scratch | Write your own `_layout.html` |

The critical distinction is whether your app includes a global `hx-select` on the main container:

- **`boost.html`** sets `hx-select="#page-content"` on `<main>`. Every response is filtered through this selector — which is correct for boosted navigation but silently discards fragment responses that don't contain `#page-content`.
- **`shell.html`** sets no `hx-select`. Fragment responses flow exactly where their `hx-target` says, with no filtering.
- **`app_shell_layout.html`** uses per-link `hx-boost` on sidebar links rather than a container-level `hx-select`, so it avoids the issue entirely for navigation while leaving fragment forms unaffected.

`chirp check` detects the mismatch automatically via the `select_inheritance` rule and warns when a mutating element may silently discard its response due to inherited `hx-select`.

## Boost Layout

The `chirp/layouts/boost.html` layout is the recommended base for htmx-boost + SSE apps:

```html
{% extends "chirp/layouts/boost.html" %}
{% block title %}My App{% end %}
{% block content %}
  <p>Page content goes here.</p>
{% end %}
{% block body_after %}
  <script>/* app-specific JS */</script>
{% end %}
```

**Structure:**

- `#main` — htmx-boost target; gets replaced on navigation
- `body_before` — above `#main` (e.g. nav bar)
- `content` — inside `#main`; page-specific HTML
- `sse_scope` — *outside* `#main`; SSE connections persist across navigations
- `body_after` — scripts, analytics

**Important:** Put `sse_scope` outside `#main`. If it's inside `content`, it gets replaced on navigation and live updates stop.

## Shell Layout

The `chirp/layouts/shell.html` layout is the base for **fragment-only apps** — pages where interactions trigger targeted fragment swaps rather than full-page boosted navigation:

```html
{% extends "chirp/layouts/shell.html" %}
{% block title %}My App{% end %}
{% block content %}
  <p>Page content goes here.</p>
{% end %}
{% block body_after %}
  <script>/* app-specific JS */</script>
{% end %}
```

Unlike `boost.html`, `shell.html` sets **no** `hx-select` on `<main>`. Forms, SSE connections, and buttons can target any element on the page without interference.

Use `shell.html` when your app:

- Returns `Fragment`, `OOB`, or `ValidationError` to specific named targets
- Does **not** use htmx-boosted sidebar navigation
- Is an LLM playground, RAG UI, dashboard form, or other targeted-swap UI

**Blocks:** `title`, `head`, `body_before`, `content`, `sse_scope`, `body_after` — identical to `boost.html` for easy migration.

### The `hx-select` Inheritance Sharp Edge

When using `boost.html`, the global `hx-select="#page-content"` on `<main>` silently discards fragment responses that don't contain a `#page-content` element. The server returns 200 OK, htmx processes the response, finds no match for the selector, and swaps in nothing. The debug panel will report "Empty hx-select."

**Symptoms:**

- Form submits return 200 OK but the UI never updates
- The HTMX debug overlay shows "Empty hx-select" for the triggering element
- Changing `hx-target` has no effect

**Fix:** Switch fragment-only apps to `shell.html`. This is a one-line change in your base template:

```html
{# Before: global hx-select causes silent empty swaps for forms #}
{% extends "chirp/layouts/boost.html" %}

{# After: no global hx-select, fragments flow where hx-target says #}
{% extends "chirp/layouts/shell.html" %}
```

Once on `shell.html`, remove any defensive `hx-disinherit="hx-select"` attributes that were working around the inherited selector — they are no longer needed.

## Outer vs Inner Content

For SSE swap targets and fragment structure:

- **Outer element** — The `sse-swap` target. Holds padding, border, layout. Stays in the DOM; its *innerHTML* is replaced.
- **Inner element** — The fragment block content. No duplicate padding or border.

```html
<!-- Outer: swap target, has padding/border; hx-target="this" when sse-connect has hx-disinherit -->
<div class="answer" sse-swap="answer" hx-target="this">
  <!-- Inner: fragment renders this; no extra padding -->
  <div class="answer-body" data-copy-text="...">
    <div class="answer-content prose">...</div>
    <button class="copy-btn">Copy</button>
  </div>
</div>
```

Avoid nesting two elements with the same padding/border — it causes double spacing. Keep `.copy-btn` in normal flow (no `position: absolute`) so it stays with its answer.

## When to Use Each Construct

| Construct | Use for |
|-----------|---------|
| `{% extends %}` | Base layout (boost, custom shell). One per template. |
| `{% block %}` | Overridable sections. Child templates fill or extend. |
| `{% include %}` | Reusable partials (headers, footers, cards). No block params. |
| `{% call %}` | Macros with parameters. Use with `{% def %}`. |

**Blocks** define slots; **includes** pull in full partials; **call/def** are parameterized components.

## Block Inheritance

Child templates override blocks by redefining them:

```html
{% extends "base.html" %}
{% block content %}
  {{ super() }}
  <p>Additional content after parent block.</p>
{% end %}
```

`{{ super() }}` renders the parent block's content. Omit it to replace entirely.

## Next Steps

- [[docs/templates/fragments|Fragments]] — Block-level rendering for htmx
- [[docs/guides/app-shell|App Shells]] — Persistent sidebar layout with SPA navigation
- [[docs/examples/rag-demo|RAG Demo]] — Full layout example with SSE and `shell.html`
