---
title: Layout Patterns
description: Template construct patterns — extends, block, include, call, and outer/inner composition
draft: false
weight: 25
lang: en
type: doc
tags: [templates, blocks, layout, composition]
keywords: [blocks, extends, include, call, super, composition]
category: guide
---

## Overview

Chirp templates use Kida's block system: `{% extends %}`, `{% block %}`,
`{% include %}`, and `{% call %}`. This guide covers patterns for using each
construct and composing pages inside a shell.

> **Pick a shell first.** Your templates `{% extends %}` one of three root
> layouts (`boost.html`, `shell.html`, or chirp-ui's `app_shell_layout.html`).
> See [Shells](/chirp/docs/guides/shells/) for the decision table and the
> `hx-select` distinction. This guide assumes a shell is already chosen.

For **fixed column ratios** on page content (`grid()` + `block(span=…)`),
see the Chirp UI package **`docs/LAYOUT-OVERFLOW.md`** (section
*Fixed columns: grid presets*).

## Extending a Shell

Whatever shell you picked, the extension shape is the same:

```html
{% extends "chirp/layouts/boost.html" %}      {# or shell.html, or chirpui/app_shell_layout.html #}
{% block title %}My App{% end %}
{% block content %}
  <p>Page content goes here.</p>
{% end %}
{% block body_after %}
  <script>/* app-specific JS */</script>
{% end %}
```

The core shells expose the same block names — `title`, `head`, `body_before`,
`content`, `sse_scope`, `body_after` — so migrating between them is a
one-line change. chirp-ui's `app_shell_layout.html` adds shell-specific
blocks (`brand`, `sidebar`, `page_root`, `page_content`); see
[App Shells](/chirp/docs/guides/app-shell/).

**Important:** Put `sse_scope` *outside* `#main`. If it's inside `content`,
it gets replaced on navigation and live updates stop.

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

- [[docs/guides/shells|Shells]] — Pick the right root layout (boost, shell, app-shell) and the `hx-select` distinction
- [[docs/templates/fragments|Fragments]] — Block-level rendering for htmx
- [[docs/guides/app-shell|App Shells]] — Persistent sidebar layout with SPA navigation
- [[docs/examples/rag-demo|RAG Demo]] — Full layout example with SSE and `shell.html`
