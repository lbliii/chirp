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
- [[docs/examples/rag-demo|RAG Demo]] — Full layout example with SSE
