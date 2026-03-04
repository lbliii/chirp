---
title: chirp-ui
description: Component library — layout, cards, forms, badges. Kida macros with CSS and themes
draft: false
weight: 25
lang: en
type: doc
tags: [guides, chirp-ui, components, kida, htmx]
keywords: [chirp-ui, components, layout, cards, forms, badges, theming]
category: guide
---

## Overview

chirp-ui is a component library for Chirp. It provides [Kida](https://lbliii.github.io/kida) template macros — cards, modals, forms, layouts — that render as HTML. Use them with htmx for swaps, SSE for streaming, and View Transitions for polish. Zero JavaScript for layout.

**What's good about it:**

- **Gorgeous by default** — Full visual design out of the box. Override `--chirpui-*` CSS variables to customize.
- **htmx-native** — Interactive components use htmx or native HTML (`<dialog>`, `<details>`). No client-side framework.
- **Composable** — `{% slot %}` for content injection. Components nest freely.
- **Modern CSS** — `:has()`, container queries, fluid typography, `prefers-color-scheme` dark mode.

## Installation

Requires Python 3.14+.

:::{tab-set}
:::{tab-item} chirp extra
```bash
pip install bengal-chirp[ui]
# or
uv add "bengal-chirp[ui]"
```
:::{/tab-item}

:::{tab-item} standalone
```bash
pip install chirp-ui
# or
uv add chirp-ui
```
:::{/tab-item}
:::{/tab-set}

## Setup

Two steps to wire chirp-ui into your app:

### 1. Wire chirp-ui into your app

Use Chirp's integration helper to serve chirpui.css, themes, transitions, and register required filters:

```python
from chirp import App, AppConfig, use_chirp_ui

app = App(AppConfig(template_dir="templates"))
use_chirp_ui(app)
```

**Import:** `use_chirp_ui` is provided by Chirp. Use `from chirp import use_chirp_ui` when the `chirp[ui]` extra is installed. If that fails (e.g. older Chirp), use `from chirp.ext.chirp_ui import use_chirp_ui`.

`use_chirp_ui(app)` adds `StaticFiles` middleware for the chirp-ui package directory (default `/static`) and registers filters (`bem`, `field_errors`, `html_attrs`, `validate_variant`) so chirp-ui components render correctly.

### 2. Include CSS in your base template

```html
<link rel="stylesheet" href="/static/chirpui.css">
```

For View Transitions support, add:

```html
<link rel="stylesheet" href="/static/chirpui-transitions.css">
```

## Auto-detection

When chirp-ui is installed, Chirp's template loader adds the chirp-ui package automatically. No configuration needed for `{% from "chirpui/..." %}` imports. Templates resolve `chirpui/layout.html`, `chirpui/card.html`, etc. from the package.

## Quick example

```html
{% from "chirpui/layout.html" import container, grid, block %}
{% from "chirpui/card.html" import card %}

{% call container() %}
    {% call grid(cols=2) %}
        {% call block() %}{% call card(title="Hello") %}<p>Card one.</p>{% end %}{% end %}
        {% call block() %}{% call card(title="World") %}<p>Card two.</p>{% end %}{% end %}
    {% end %}
{% end %}
```

## App Shell

**Quick start:** Extend `chirpui/app_shell_layout.html` and fill the blocks. No manual HTML boilerplate:

```html
{# target: body #}
{% extends "chirpui/app_shell_layout.html" %}
{% block brand %}My App{% end %}
{% block sidebar %}
  {% from "chirpui/sidebar.html" import sidebar, sidebar_link, sidebar_section %}
  {% call sidebar() %}
    {% call sidebar_section("Main") %}
      {{ sidebar_link("/", "Home") }}
      {{ sidebar_link("/items", "Items") }}
    {% end %}
  {% end %}
{% end %}
```

**Adding an inner shell:** For nested layouts (e.g. forum > subforum), use the `shell_section` macro from Chirp:

```html
{% from "chirp/macros/shell.html" import shell_section %}
{% call shell_section("forum-content") %}
  {% block content %}{% end %}
{% end %}
```

**Migrating from boost.html:** Replace `{% extends "chirp/layouts/boost.html" %}` with `{% extends "chirpui/app_shell_layout.html" %}`. Add `{% block brand %}`, `{% block sidebar %}`, etc. The `hx-select="#page-content"` and `id="page-content"` are already in place.

**Manual shell:** For full control, chirp-ui provides components for building persistent dashboard shells: `sidebar`, `breadcrumbs`, and `command_palette`. Combine them in a standalone `_layout.html`:

```html
{# target: main #}
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>My Dashboard</title>
  <script src="https://unpkg.com/htmx.org@2.0.4"></script>
  <link rel="stylesheet" href="/static/chirpui.css">
</head>
<body>
{% from "chirpui/sidebar.html" import sidebar, sidebar_section, sidebar_link %}
{% from "chirpui/breadcrumbs.html" import breadcrumbs %}
{% from "chirpui/command_palette.html" import command_palette, command_palette_trigger %}
{% from "chirpui/toast.html" import toast_container %}

{% set cp = current_path | default("/") %}

<div class="chirpui-app-shell">
  <header class="chirpui-app-shell__topbar">
    <a href="/" class="chirpui-app-shell__brand">My App</a>
    <div class="chirpui-app-shell__topbar-center">
      {{ breadcrumbs(breadcrumb_items | default([{"label": "Home", "href": "/"}])) }}
    </div>
    <div class="chirpui-app-shell__topbar-end">
      {{ command_palette_trigger() }}
    </div>
  </header>
  <aside class="chirpui-app-shell__sidebar">
    {% call sidebar() %}
      {% call sidebar_section("Navigate") %}
        {{ sidebar_link("/", "Home", active=cp == "/") }}
        {{ sidebar_link("/items", "Items", active=cp.startswith("/items")) }}
      {% end %}
    {% end %}
  </aside>
  <main id="main" class="chirpui-app-shell__main"
        hx-boost="true" hx-target="#main"
        hx-swap="innerHTML transition:true"
        hx-select="#page-content">
    <div id="page-content">
      {% block content %}{% end %}
    </div>
  </main>
</div>

{{ command_palette(search_url="/search") }}
{{ toast_container() }}
</body>
</html>
```

**Why standalone?** Chirp's `render_with_blocks({"content": ...})` replaces `{% block content %}` entirely. If you extend `boost.html` and put the shell inside `{% block content %}`, it gets overwritten. A standalone layout puts the shell outside the content block so it always renders. See [[docs/routing/filesystem-routing|Filesystem Routing]] for the full explanation.

**Why `hx-select`?** On htmx-boosted navigation, Chirp returns a full HTML page (it renders the matched layout). Without `hx-select`, htmx would swap the entire response into `#main`, replacing the shell. `hx-select="#page-content"` tells htmx to parse the response and extract only `#page-content` — the shell stays untouched.

**Why no `hx-disinherit`?** Boosted links inside the content area need to inherit `hx-target="#main"`, `hx-swap`, and `hx-select` from the `<main>` element. If you add `hx-disinherit`, boosted links fall back to targeting `body`, which replaces everything. Fragment requests with explicit `hx-target` (e.g. `hx-target="#compare-result"`) override the inherited value naturally.

## Component categories

| Category | Examples |
|----------|----------|
| **Layout** | container, grid, stack, block, page_header, section_header, divider, breadcrumbs, navbar, sidebar, hero, surface, callout |
| **UI** | card, card_header, modal, drawer, tabs, accordion, dropdown, popover, toast, table, pagination, alert, button_group |
| **Forms** | text_field, password_field, textarea_field, select_field, checkbox_field, toggle_field, radio_field, file_field, date_field, csrf_hidden, form_actions, login_form, signup_form |
| **Data display** | badge, spinner, skeleton, progress, description_list, timeline, tree_view, calendar |
| **Streaming** | streaming_block, copy_btn, model_card — for htmx SSE and LLM UIs |

See the [chirp-ui repository](https://github.com/lbliii/chirp-ui) for the full component reference and API.

## Theming

chirp-ui uses `prefers-color-scheme` for dark mode. Override any `--chirpui-*` variable:

```css
:root {
    --chirpui-accent: #7c3aed;
    --chirpui-container-max: 80rem;
}
```

For manual light/dark toggle, set `data-theme="light"` or `data-theme="dark"` on `<html>`.

Optional theme: `<link rel="stylesheet" href="/static/themes/holy-light.css">`

## chirp new

When chirp-ui is installed, `chirp new <name>` scaffolds a project with `use_chirp_ui(app)` wired in the app module. The base template includes chirpui.css.

## Next steps

- [chirp-ui on GitHub](https://github.com/lbliii/chirp-ui) — Full component reference, showcase app, and development docs
- [[docs/examples/rag-demo|RAG Demo]] — Uses chirp-ui for layout, cards, badges, and alert
- [[docs/guides/islands|Islands Contract]] — chirp-ui provides `island_root` and state primitives for high-state widgets
