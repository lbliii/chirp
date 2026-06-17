---
title: Layout Patterns
description: Compose Chirp pages from Kida template constructs — extends, block, include, and call
draft: false
weight: 25
lang: en
type: doc
tags: [templates, blocks, layout, composition]
keywords: [blocks, extends, include, call, super, composition]
category: guide
---

## Overview

Chirp templates are [[docs/build-apps/html-fragments/kida-integration|Kida]]
templates. You compose a page from four constructs:

- `{% extends %}` — inherit a root layout (shell).
- `{% block %}` — fill or extend an overridable slot the layout left open.
- `{% include %}` — pull in a partial (a header, footer, or card).
- `{% call %}` — invoke a parameterized macro defined with `{% def %}`.

This page shows the idiomatic pattern for each and how page content nests inside
a shell.

:::{note}
New to which root layout to pick? A shell is the outermost template your pages
`{% extends %}` — `boost.html`, `shell.html`, or chirp-ui's
`app_shell_layout.html`. Start at [[docs/build-apps/ui-extensions/shells|Shells]]
for the decision table and the `hx-select` distinction. This page assumes you
have already chosen one.
:::

## When to reach for each construct

:::{list-table}
:header-rows: 1

* - Construct
  - Use for
* - `{% extends %}`
  - The root layout for a page. One per template.
* - `{% block %}`
  - Overridable sections. A child template fills a block, or extends it with `{{ super() }}`.
* - `{% include %}`
  - Reusable partials (headers, footers, cards). No parameters.
* - `{% call %}`
  - Parameterized components. Pair with `{% def %}` to define the macro.
:::

Blocks define slots; includes pull in full partials; `call`/`def` are
parameterized components.

## Extend a shell

Whatever shell you picked, the extension shape is the same — name the layout,
then fill its blocks:

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

Every root layout exposes `title`, `head`, `content`, `sse_scope`, and
`body_after` (plus `lang`). Beyond that shared set, the layouts differ: switching
from one shell to another is not always a no-op.

:::{list-table}
:header-rows: 1

* - Shell
  - Blocks beyond the shared set
* - `boost.html`
  - `body_before`, `head_style`
* - `shell.html`
  - `scripts`, `shell`
* - chirp-ui `app_shell_layout.html`
  - `brand`, `sidebar`, `topbar_leading`, `topbar_center`, `topbar_end`, `context_rail`, `head_extra`, `page_scripts`
:::

If a page fills `body_before` on `boost.html` and you move it to `shell.html`,
that block silently does nothing — `shell.html` has no `body_before`. Check the
target shell's blocks before migrating. For the chirp-ui layout blocks
(`brand`, `sidebar`, and the topbar slots), see
[[docs/build-apps/ui-extensions/app-shell|App Shells]].

`page_root` and `page_content` are **not** `app_shell_layout.html` blocks. They
are page-composition blocks your page defines, injected into the layout's
`content` block — not layout overrides. A template that
`{% extends "chirpui/app_shell_layout.html" %}` and writes `{% block page_root %}`
gets a silent no-op, the same trap as `body_before` above.

:::{warning}
Put `sse_scope` *outside* the `content` block. If it lives inside `content`, it
gets replaced on navigation and live updates stop firing. Every root layout
already declares `sse_scope` at the top level for this reason.
:::

## Override and extend blocks

A child template overrides a block by redefining it. To build on the parent's
content instead of replacing it, call `{{ super() }}`:

```html
{% extends "base.html" %}
{% block content %}
  {{ super() }}
  <p>Additional content after the parent block.</p>
{% end %}
```

`{{ super() }}` renders the parent block's content in place. Omit it to replace
the block entirely.

## Mounted pages compose, they do not inherit

Filesystem [[docs/build-apps/pages-navigation/filesystem-routing|pages]] are
different from the `{% extends %}` flow above. A `page.html` does **not**
`{% extends %}` its sibling `_layout.html`. Instead Chirp composes them: page
HTML is injected into the layout's `{% block content %}` via the internal
`render_with_blocks` pass.

Because there is no inheritance link, a page template **cannot** override a
layout block such as `page_scripts` or `head_extra` — those slots belong to
templates that `{% extends %}` the layout directly. If a mounted page needs an
inline `<script>`, place it inside the content region (inside `page_root` or
`page_content`), not in a sibling layout block.

## Advanced

::::{dropdown} SSE swap-target structure (outer vs inner)
When a block is the target of an [[docs/build-apps/streaming-updates/server-sent-events|SSE]]
swap, split the markup into two elements so updates do not double up padding or
borders:

- **Outer element** — the `sse-swap` target. Holds padding, border, and layout.
  It stays in the DOM; its `innerHTML` is replaced.
- **Inner element** — the fragment block content. Carries no duplicate padding
  or border.

```html
<!-- Outer: swap target, has padding/border; hx-target="this" when sse-connect has hx-disinherit -->
<div class="answer" sse-swap="answer" hx-target="this">
  <!-- Inner: the fragment renders this; no extra padding -->
  <div class="answer-body" data-copy-text="...">
    <div class="answer-content prose">...</div>
    <button class="copy-btn">Copy</button>
  </div>
</div>
```

Avoid nesting two elements with the same padding or border — it causes double
spacing. Keep `.copy-btn` in normal flow (no `position: absolute`) so it stays
with its answer. For the full SSE fragment-structure playbook, see
[[docs/build-apps/streaming-updates/sse-patterns|SSE patterns]].
::::{/dropdown}

:::{note} See also
- [[docs/build-apps/ui-extensions/shells|Shells]] — pick the right root layout and the `hx-select` distinction
- [[docs/build-apps/html-fragments/fragments|Fragments]] — block-level rendering for htmx
- [[docs/build-apps/ui-extensions/app-shell|App Shells]] — persistent sidebar layout with SPA navigation
- [[docs/build-apps/streaming-updates/sse-patterns|SSE patterns]] — swap-target structure for live updates
- [[docs/examples/rag-demo|RAG Demo]] — full layout example with SSE on the chirp-ui `app_shell_layout`
:::
