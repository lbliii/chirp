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

### 1. Serve static assets

Use Chirp's integration helper to serve chirpui.css, themes, and transitions:

```python
from chirp import App, AppConfig
from chirp.ext.chirp_ui import use_chirp_ui
import chirp_ui

app = App(AppConfig(template_dir="templates"))
use_chirp_ui(app)
chirp_ui.register_filters(app)
```

`use_chirp_ui(app)` adds `StaticFiles` middleware for the chirp-ui package directory. By default it serves at `/static`. Pass `prefix="/assets"` to change it.

### 2. Register filters

`chirp_ui.register_filters(app)` registers `bem` and `field_errors` so chirp-ui components (badge, alert, form fields) work correctly. Call it after `use_chirp_ui`.

### 3. Include CSS in your base template

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

When chirp-ui is installed, `chirp new <name>` scaffolds a project with `use_chirp_ui(app)` and `chirp_ui.register_filters(app)` already wired in the app module. The base template includes chirpui.css.

## Next steps

- [chirp-ui on GitHub](https://github.com/lbliii/chirp-ui) — Full component reference, showcase app, and development docs
- [[docs/examples/rag-demo|RAG Demo]] — Uses chirp-ui for layout, cards, badges, and alert
- [[docs/guides/islands|Islands Contract]] — chirp-ui provides `island_root` and state primitives for high-state widgets
