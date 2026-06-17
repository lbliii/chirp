---
title: UI layers & shell regions
description: A shared vocabulary for app shell, page chrome, and surface chrome, plus swap_attrs for resolving hx-target from route geometry
draft: false
weight: 34
lang: en
type: doc
tags: [app-shell, htmx, layout, swap-scopes]
keywords: [shell, chrome, page-content, OOB, fragment targets, swap scope, swap_attrs]
category: guide
---

## Overview

A persistent **app shell** is a fixed topbar and sidebar that stays put while the inner content swaps. The moment you have a shell, every link needs an answer to one question: *how wide does this swap go?* Does clicking it repaint the whole shell, just the page body, or only a panel inside the page?

This page gives you a shared name for each of those widths — **app shell**, **page chrome**, **surface chrome** — and shows how to author links with the `swap_attrs` template global so Chirp resolves the right `hx-target` from your route layout, instead of you hard-coding DOM ids on every link.

:::{note}
If you only have a single fixed sidebar, start with [[docs/build-apps/ui-extensions/app-shell|App shells]] and [[docs/build-apps/ui-extensions/boosted-navigation|boosted navigation]] — they cover the common case without scopes. Come back here when you have more than one swap level and links are swapping too much (the whole shell flickers) or too little (an inner panel never updates).
:::

## The four layers

Chirp and chirp-ui use the words *shell* and *chrome* a lot. Here is the one vocabulary the docs, the APIs, and your templates all share. Read it top-down: each layer swaps a narrower slice of the page than the one above it.

:::{list-table}
:header-rows: 1

* - Layer
  - Name
  - Swap scope
  - Where it lives
  - Updates on
* - **L1**
  - **App shell**
  - `shell`
  - Topbar, sidebar, the `#main` wrapper — everything outside `#page-content`
  - Boosted navigation plus out-of-band swaps for shell regions
* - **L2**
  - **Shell outlet**
  - `shell`
  - `#page-content`, inside `#main`
  - Boosted navigation (via `hx-select`)
* - **L3**
  - **Page chrome**
  - `page`
  - Headers, tabs, and toolbars inside `#page-content`
  - Page-level fragment targets such as `#page-root`
* - **L4**
  - **Surface chrome**
  - `content`
  - The border, padding, and scroll area around a single component (a card, panel, or bento cell)
  - Local swaps only — never the app shell
:::

:::{warning}
**"Shell" means L1 — the persistent frame — everywhere.** Do not call a card's border or padding "shell"; that is **surface chrome** (L4).

One related footgun: a Kida block named `page_root` does **not** emit `id="page-root"`. The element is what `#page-root` swaps target, so if you name the block but omit the `id`, page-level swaps silently fail — even while boosted navigation still works through `#page-content`.
:::

## Resolve the target with `swap_attrs`

Each layout level can declare a **swap scope**: a stable name for "how wide a swap happens here." Scopes let you author a link once and have Chirp pick the `hx-target`, instead of memorizing which DOM id is correct from each page.

The `swap_attrs(href)` template global computes the nearest shared navigation boundary between the current path and the destination, then returns the `hx-target` (and `hx-boost`) for that link. Pipe it through `html_attrs` to render the attributes. An explicit `hx-target` on the element always wins.

::::{code-tabs}
:sync: links

```html
<!-- Hand-coded: you must know the right id for every link -->
<a href="/dashboard/reports"
   hx-target="#main"
   hx-boost="true">Reports</a>
```

```html
<!-- swap_attrs: Chirp resolves the target from the route layout chain -->
<a href="/dashboard/reports"
   {{ swap_attrs("/dashboard/reports") | html_attrs }}>Reports</a>
```

::::

When chirp-ui is active, `swap_attrs` is registered for you and bound to these three well-known scopes:

| Scope | Typical role | Default target id |
|-------|--------------|-------------------|
| `shell` | L1–L2: swap inside site chrome | `main` |
| `page` | L3: tabbed or page chrome | `page-root` |
| `content` | L4: narrow in-page swap | `page-content-inner` |

### Register a custom scope

Apps can add their own scope name beyond the three defaults. Register it during setup, mapping the scope to a concrete target id (no `#` prefix — Chirp strips it):

```python
app.register_swap_scope("section", "section-outlet")
```

### A two-domain nested shell

A common layout is a marketing site that wraps a chirp-ui app: a public outer shell with its own header and footer, and an inner application shell with a sidebar. Each declares its own **navigation domain**, and `swap_attrs` reads the domains to decide where a swap lands:

1. **Outer site shell** (`pages/_layout.html`, `{# domain: site #}`) — site header, footer, and a `#site-content` outlet.
2. **Inner app shell** (`pages/app/_layout.html`, `{# domain: app #}`) — the chirp-ui `app_shell()` with sidebar, breadcrumbs, and `shell_outlet()`.

Navigating from `/` to `/app` swaps at the **site** level (`#site-content`). Navigating within `/app/*` swaps at the **app** level (the inner outlet). `swap_attrs` derives both from the layout chains — you do not set `hx-target` by hand.

## Shell regions (stable OOB targets)

Shell **regions** are elements with fixed `id` attributes that htmx updates with [[docs/quality/contracts-debugging/oob-registry|out-of-band swaps]] *after* the primary `#main` swap — the document title, route-scoped topbar actions, breadcrumbs. Chirp ships canonical ids in the `chirp.shell_regions` module so tooling and tests agree on the spelling:

| Constant | Default element id | Role |
|----------|--------------------|------|
| `DOCUMENT_TITLE_ELEMENT_ID` | `chirpui-document-title` | The `<title>` element |
| `SHELL_ACTIONS_TARGET` | `chirp-shell-actions` | Route-scoped topbar actions |

`SHELL_ELEMENT_IDS` is a frozenset of those documented ids. Apps may add their own OOB targets (sidebars, extra breadcrumb trails); register them with `app.register_oob_region(...)` and document the ids locally.

A fragment target's `triggers_shell_update` flag controls whether swapping it reruns shell negotiation (the `shell_actions` OOB pass). It defaults to `True`; set it `False` for narrow in-page swaps — for example `#page-content-inner` — that should not refresh the topbar.

When a swap targets a specific scope (say `page`), layout OOB blocks fire only for layouts at or above that scope's depth: the matched shell and its ancestors, never sibling or descendant shells. Boosted navigation with no explicit `hx-target` fires OOB at every level.

## Validate at startup

`app.check()` validates your scope and layout metadata at freeze time and reports duplicate swap scopes, missing outlets, frame-versus-swap conflicts, and conflicting outlets before they ship.

:::{note} See also
- [[docs/quality/contracts-debugging/categories|Contract categories]] — the full list of layout checks and their severities
:::

## Advanced

::::{dropdown} Layout-comment metadata reference
Filesystem `_layout.html` files declare their scope and outlet metadata through Kida template comments, parsed at discovery time:

```html
{# target: body #}
{# domain: site #}
{# swap_scope: shell #}
{# outlet: site-content #}
{# frames: site-header, site-footer #}
```

| Comment | Purpose |
|---------|---------|
| `{# target: id #}` | DOM element this layout renders into (required) |
| `{# domain: name #}` | Explicit navigation-domain boundary for `swap_attrs` |
| `{# swap_scope: name #}` | Symbolic scope used when resolving navigation swaps |
| `{# outlet: id #}` | Primary navigation outlet id for this level |
| `{# frames: id, id #}` | Immutable frame ids — contract-checked so they are never swap targets |

For **filesystem** apps, the root `_layout.html` should declare `{# outlet: main #}` alongside `{# target: body #}`, so Chirp resolves `HX-Target: #main` and returns the full shell including `#page-content`. See [[docs/build-apps/pages-navigation/filesystem-routing|Filesystem routing]].
::::{/dropdown}

::::{dropdown} hx-select wiring and swap ordering
`#main` participates in boosted navigation; the fragment `hx-select` depends on the layout:

| Layout | `hx-select` on `#main` | Required in page HTML |
|--------|------------------------|------------------------|
| `chirpui/app_shell_layout.html` | `#page-content` | A `<div id="page-content">` wrapper with `#page-root` inside |
| `chirpui/app_shell.html` custom shells | `#page-content` via `shell_outlet()` | `shell_outlet()` wrapping the routed content block |
| `chirp/layouts/boost.html` | `#page-content` | The layout's `#page-content` wrapper |

htmx applies the **primary** swap before any **out-of-band** fragments. chirp-ui's `app_shell_layout.html` ships a small `htmx:beforeSwap` handler that clears `#chirp-shell-actions` when the response carries a matching OOB swap, avoiding one frame of stale topbar actions.
::::{/dropdown}

:::{note} See also
- [[docs/build-apps/ui-extensions/shells|Shells overview]] — when to reach for a custom shell
- [[docs/build-apps/ui-extensions/app-shell|App shells]] — the chirp-ui navigation model and `use_chirp_ui`
- [[docs/build-apps/ui-extensions/boosted-navigation|Boosted navigation]] — how full-page links become fragment swaps
:::

:::{related}
:::
