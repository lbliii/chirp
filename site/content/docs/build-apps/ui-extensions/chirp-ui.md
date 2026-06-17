---
title: chirp-ui
description: The official Chirp component library — Kida macros for cards, forms, modals, and an app shell that render to styled HTML with no build step
draft: false
weight: 25
lang: en
type: doc
tags: [guides, chirp-ui, components, kida, htmx]
keywords: [chirp-ui, components, layout, cards, forms, badges, theming, app shell, route tabs]
category: guide
---

## Overview

chirp-ui is the official component library for Chirp: a set of
[Kida](https://lbliii.github.io/kida) template macros — cards, forms, modals,
layouts, an app shell — that render to styled HTML with no build step and no
client framework. Reach for it when you want a good-looking app out of the box
and want interactivity to come from [[docs/build-apps/html-fragments/fragments|htmx swaps]]
and native HTML (`<dialog>`, `<details>`) rather than a JavaScript framework.

Install the `chirp[ui]` extra, call `use_chirp_ui(app)`, and import the macros
you need — the framework wires up the CSS, themes, and template filters for you.

It gives you:

- **A full visual design out of the box.** Override `--chirpui-*` CSS variables to customize.
- **htmx-native interactivity.** Components use htmx or native HTML (`<dialog>`, `<details>`) — no client-side framework.
- **Composable macros.** `{% slot %}` for content injection; components nest freely.
- **Modern CSS.** `:has()`, container queries, fluid typography, and `prefers-color-scheme` dark mode.

## Installation

:::{since} 0.10.0
The `chirp[ui]` extra pulls in `chirp-ui>=0.10.0`. Requires Python 3.14+.
:::

:::{tab-set}
:::{tab-item} chirp extra
```bash
pip install "bengal-chirp[ui]"
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

::::{steps}
:::{step} Wire chirp-ui into your app
Call `use_chirp_ui(app)` after creating the app. It serves `chirpui.css`,
themes, and transitions, and registers the filters chirp-ui components need
(`bem`, `field_errors`, `html_attrs`, `validate_variant`).

```python
from chirp import App, AppConfig, use_chirp_ui

app = App(AppConfig(template_dir="templates"))
use_chirp_ui(app)
```

`use_chirp_ui` ships with the `chirp[ui]` extra. If `from chirp import
use_chirp_ui` fails on an older Chirp, import it from `chirp.ext.chirp_ui`
instead.
:::{/step}

:::{step} Include the CSS in your base template
```html
<link rel="stylesheet" href="/static/chirpui.css">
```

For View Transitions, also add:

```html
<link rel="stylesheet" href="/static/chirpui-transitions.css">
```
:::{/step}
::::{/steps}

:::{warning} use_chirp_ui changes your app config
`use_chirp_ui` auto-enables Alpine.js (chirp-ui components require it) and wires
a per-request nonce CSP so the inline Alpine survives secure-by-default headers.
It does **not** auto-enable htmx — the chirp-ui shell layouts already ship their
own htmx `<script>`. If you also set `AppConfig(htmx=True)`, the injector's dedup
skips re-adding the core script, so you will not double-load. See
[[docs/build-apps/ui-extensions/alpine|Alpine.js integration]] for how Chirp owns
Alpine injection.
:::

### Template auto-detection

When chirp-ui is installed, Chirp's template loader adds the chirp-ui package
automatically. No configuration is needed for `{% from "chirpui/..." %}`
imports — `chirpui/layout.html`, `chirpui/card.html`, and the rest resolve from
the package.

## Quick example

A two-card grid in a centered container:

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

## App shell

The fastest way to a sidebar-and-topbar app is to extend chirp-ui's
`app_shell_layout.html` and fill its blocks. No manual HTML boilerplate, and the
htmx-boost navigation contract is already wired:

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

:::{warning} Put shell chrome outside `{% block content %}`
Chirp's `render_with_blocks` replaces `{% block content %}` on every render. Any
sidebar, topbar, or breadcrumbs you place *inside* the content block get wiped on
the next navigation. `app_shell_layout.html` already puts the chrome outside the
content outlet — if you build a shell by hand, keep it that way.
:::

:::{note} See also
- [[docs/build-apps/ui-extensions/shells|Shells decision guide]] — pick between `boost.html`, `shell.html`, and `app_shell_layout.html`.
- [[docs/build-apps/ui-extensions/app-shell|App Shell guide]] — the full guide to `app_shell_layout.html`, regions, and OOB blocks.
- [[docs/build-apps/ui-extensions/boosted-navigation|Boosted navigation]] — the `hx-select` swap contract and debug warnings.
- [[docs/build-apps/html-fragments/layout-patterns|Layout Patterns]] — how page content composes into a shell.
:::

:::{dropdown} Build the shell by hand
For full control, compose the shell from individual chirp-ui macros —
`sidebar`, `breadcrumbs`, and `command_palette` — in a standalone `_layout.html`.
The boost attributes on `<main>` are what make plain `<a href>` links navigate
without a full reload.

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
  <main id="main" class="chirpui-app-shell__main" tabindex="-1"
        hx-boost="true" hx-target="#main"
        hx-swap="innerHTML" hx-select="#page-content">
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

The boost contract here — `hx-target="#main"`, `hx-swap="innerHTML"`,
`hx-select="#page-content"` — keeps the shell chrome untouched while only the
inner fragment swaps. The reasoning behind each attribute lives in
[[docs/build-apps/ui-extensions/boosted-navigation|Boosted navigation]].
:::

:::{dropdown} Nested (inner) shells
For layouts within layouts — e.g. a forum that frames each subforum — wrap a
region with the `shell_section` macro:

```html
{% from "chirp/macros/shell.html" import shell_section %}
{% call shell_section("forum-content") %}
  {% block content %}{% end %}
{% end %}
```
:::

:::{dropdown} Page spacing for boosted navigation
Let the page-level wrapper own vertical rhythm: a parent layout with a
`page_root` block holding `container()` + `stack(gap="lg")`, and inner blocks
like `page_content` for the page-specific sections. Pair that with a wide page
block so boosted navigation swaps the full page shell, not a too-narrow inner
fragment:

```python
return Page("dashboard.html", "page_content", page_block_name="page_root", **ctx)
```

For explicit fragment/page/region composition, `PageComposition` exposes the
same idea via `fragment_block=` and `page_block=`. See
[[docs/about/core-concepts/return-values|return types]] for when each applies.
:::

:::{dropdown} Migrating from boost.html
Replace `{% extends "chirp/layouts/boost.html" %}` with
`{% extends "chirpui/app_shell_layout.html" %}`, then add `{% block brand %}`,
`{% block sidebar %}`, and the other shell blocks. The `hx-select="#page-content"`
and `id="page-content"` are already in place.

If your app uses forms or SSE but no sidebar navigation, extend
`chirp/layouts/shell.html` instead. Unlike `boost.html`, `shell.html` sets no
global `hx-select`, so fragment responses flow directly to their `hx-target`
with no risk of silent empty swaps — see
[[docs/build-apps/ui-extensions/shells|Shells]].
:::

### Route tabs

To drive a tab bar from your route structure, register `Section.tab_items` in
Python and set `RouteMeta.section` in each route's `_meta.py`. Chirp injects
`tab_items` / `route_tabs` into the template context and registers the
`tab_is_active` helper. The `render_route_tabs` macro is provided by the
chirp-ui package. See the
[shell, sections, and route-tabs contract](https://github.com/lbliii/chirp-ui/blob/main/docs/SHELL-TABS-CONTRACT.md)
for targets, boost behavior, and `app.check()` expectations.

## Component categories

:::{list-table}
:header-rows: 1

* - Category
  - Macros
* - **Layout**
  - container, grid, stack, block, page_header, section_header, divider, breadcrumbs, navbar, sidebar, hero, surface, callout
* - **UI**
  - card, card_header, modal, drawer, tabs, accordion, dropdown, popover, toast, table, pagination, alert, button_group
* - **Forms**
  - text_field, password_field, textarea_field, select_field, checkbox_field, toggle_field, radio_field, file_field, date_field, csrf_hidden, form_actions, login_form, signup_form
* - **Data display**
  - badge, spinner, skeleton, progress, description_list, timeline, tree_view, calendar
* - **Streaming**
  - streaming_block, copy_btn, model_card — for htmx SSE and LLM UIs
:::

See the [chirp-ui repository](https://github.com/lbliii/chirp-ui) for the full
component reference and API.

## Data layout patterns

For dashboard and settings pages, these patterns give consistent structure.

### Section with header actions

Put section-level buttons (Refresh, Auto-detect, Run validation) in the
`section` actions slot, not beneath the content:

```html
{% from "chirpui/layout.html" import section %}
{% from "chirpui/button.html" import btn %}
{% call section("Setup targets", subtitle="Configure your IDE") %}
{% slot actions %}{{ btn("Refresh", attrs_map={"hx-get": "/status", "hx-target": "#targets"}) }}{% end %}
<div id="targets">...</div>
{% end %}
```

### Settings rows

For label + status + value (e.g. setup targets, health checks), use
`settings_row_list` and `settings_row`:

```html
{% from "chirpui/settings_row.html" import settings_row_list, settings_row %}
{% call settings_row_list() %}
{{ settings_row("Cursor IDE", status="Configured", detail="setup cursor") }}
{{ settings_row("Skills directory", status="ok", detail="/path/to/skills") }}
{% end %}
```

Use `description_list` for term + detail only (no status badge); use
`settings_row_list` when you have label + status + detail.

## Theming

chirp-ui uses `prefers-color-scheme` for dark mode. Override any `--chirpui-*`
variable:

```css
:root {
    --chirpui-accent: #7c3aed;
    --chirpui-container-max: 80rem;
}
```

For a manual light/dark toggle, set `data-theme="light"` or `data-theme="dark"`
on `<html>`. To load an alternate theme, add its stylesheet:

```html
<link rel="stylesheet" href="/static/themes/holy-light.css">
```

## Scaffolding

When chirp-ui is installed, `chirp new <name>` scaffolds a project with
`use_chirp_ui(app)` already wired into the app module and `chirpui.css` linked
in the base template.

## Next steps

- [[docs/examples/rag-demo|RAG Demo]] — uses chirp-ui for layout, cards, badges, and alerts.
- [[docs/build-apps/ui-extensions/app-shell|App Shell guide]] — build a persistent sidebar/topbar app.
- [[docs/build-apps/ui-extensions/islands|Islands]] — chirp-ui's `island_root` and state primitives for high-state widgets.
- [chirp-ui on GitHub](https://github.com/lbliii/chirp-ui) — full component reference, showcase app, and development docs.

:::{related}
:::
