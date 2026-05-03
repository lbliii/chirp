---
title: UI layers & shell regions
description: Vocabulary for app shell, page chrome, surface chrome, symbolic swap scopes, and stable OOB targets
draft: false
weight: 34
lang: en
type: doc
tags: [app-shell, htmx, layout, glossary, swap-scopes]
keywords: [shell, chrome, page-content, OOB, fragment targets, swap scope, swap_attrs]
category: guide
---

## Why this page exists

Chirp + chirp-ui use several overlapping words (**shell**, **chrome**, **fragments**, **scopes**). This guide fixes one vocabulary for docs, APIs, and templates.

## The four layers

| Layer | Official term | Symbolic scope | Where it lives | Updates when |
|-------|---------------|---------------|----------------|--------------|
| **L1** | **App shell** | ``shell`` | Topbar, sidebar, wrapper ``#main`` — outside ``#page-content`` | Boosted navigation + OOB for shell regions |
| **L2** | **Shell outlet** | ``shell`` | ``#page-content`` inside ``#main`` | Boosted navigation (``hx-select``) |
| **L3** | **Page chrome** | ``page`` | Inside ``#page-content`` (headers, tabs, route toolbars) | Broader fragment targets (e.g. ``#page-root``) |
| **L4** | **Surface chrome** | ``content`` | Borders/padding/scroll around **components** (cards, panels, bento cells) | Local swaps only — *not* the app shell |

**Rule:** In prose and APIs, **shell** means **L1** (persistent frame). Do not call card borders "shell"; use **surface chrome**.

## Symbolic swap scopes

Each layout level can declare a **symbolic swap scope** — a stable name for "what width of swap happens at this level." Scopes decouple link authoring from DOM id details.

| Scope name | Typical role | Default target id (chirp-ui) |
|------------|-------------|------------------------------|
| ``shell`` | L1–L2: swap inside site chrome | ``#main`` |
| ``page`` | L3: tabbed/page chrome | ``#page-root`` |
| ``content`` | L4: narrow in-page swap | ``#page-content-inner`` |

Apps can define **custom scope names** (e.g. ``section`` for a showcase shell) beyond these three well-known defaults. Register them during setup:

```python
app.register_swap_scope("section", "showcase-outlet")
```

### Layout comments

Filesystem ``_layout.html`` files declare scope metadata via template comments:

```html
{# target: body #}
{# domain: site #}
{# swap_scope: shell #}
{# outlet: site-content #}
{# frames: site-header, site-footer #}
```

| Comment | Purpose |
|---------|---------|
| ``{# target: id #}`` | DOM element this layout renders into (required) |
| ``{# domain: name #}`` | Explicit navigation-domain boundary for `swap_attrs()` |
| ``{# swap_scope: name #}`` | Symbolic scope for ``resolve_navigation_swap`` |
| ``{# outlet: id #}`` | Primary navigation outlet id for this level |
| ``{# frames: id, id #}`` | Immutable frame ids (contract-checked: must not be swap targets) |

### ``swap_attrs`` template global

Instead of hand-coding ``hx-target`` on every link, use ``swap_attrs`` to resolve the correct target from route geometry:

```html
{# Before: author must know the right id #}
<a href="/showcase/products" hx-target="#main" hx-boost="true">Products</a>

{# After: framework resolves from current path + destination layout chain #}
<a href="/showcase/products" {{ swap_attrs("/showcase/products") | html_attrs }}>Products</a>
```

``swap_attrs(href)`` computes the nearest shared navigation boundary between the current
path and destination, then returns ``{"hx-target": "#main", "hx-boost": "true"}``
(or broader/narrower, depending on context). When layouts declare ``{# domain: #}``,
domain ancestry drives the decision. Otherwise Chirp falls back to legacy shell/layout
geometry. Pipe through ``html_attrs`` to render as HTML attributes. Explicit
``hx-target`` on the element always overrides the resolved value.

### Nested shell example (b-site)

b-site uses two nested shells and two explicit navigation domains:

1. **Root marketing shell / site domain** (``pages/_layout.html``, ``{# domain: site #}``) — site header, footer, ``#site-content`` outlet
2. **Showcase app shell / showcase domain** (``pages/showcase/_layout.html``, ``{# domain: showcase #}``) — chirp-ui ``app_shell()`` with sidebar, breadcrumbs, ``shell_outlet()``

Navigation from ``/`` to ``/showcase`` swaps at the **site** level (``#site-content``). Navigation within ``/showcase/*`` swaps at the **showcase** level (inner outlet). ``swap_attrs`` derives this automatically from the layout chains.

## Boosted navigation and ``hx-select``

``#main`` participates in boosted navigation; the fragment selector depends on the layout:

| Layout | ``hx-select`` on ``#main`` | Required in page HTML |
|--------|---------------------------|------------------------|
| ``chirpui/app_shell_layout.html`` | ``#page-content`` | ``<div id="page-content">…`` wrapper with ``#page-root`` inside |
| ``chirpui/app_shell.html`` custom shells | ``#page-content`` via ``shell_outlet()`` | ``shell_outlet()`` wraps the routed content block |
| ``chirp/layouts/boost.html`` | ``#page-content`` | The layout's ``#page-content`` wrapper |

For **filesystem** apps, root ``_layout.html`` should declare ``{# outlet: main #}`` (with ``{# target: body #}``) so Chirp resolves ``HX-Target: #main`` and returns full shell HTML including ``#page-content``. See [[docs/routing/filesystem-routing|Filesystem routing]].

``page_root`` remains the broader page-level fragment target inside the shell outlet. A block named ``page_root`` does **not** create ``id="page-root"``; omitting that element breaks ``#page-root`` swaps even when boosted navigation still works through ``#page-content``.

## Shell regions (stable DOM ids)

Shell **regions** are elements with fixed ``id`` attributes that htmx updates with **out-of-band** swaps after the primary ``#main`` swap. Import canonical ids from :mod:`chirp.shell_regions`:

| Constant | Default element id | Role |
|----------|-------------------|------|
| ``DOCUMENT_TITLE_ELEMENT_ID`` | ``chirpui-document-title`` | Document title (``<title>``) |
| ``SHELL_ACTIONS_TARGET`` | ``chirp-shell-actions`` | Route-scoped topbar actions |

``SHELL_ELEMENT_IDS`` is a frozenset of documented ids for tooling and tests.

Apps may add more OOB targets (breadcrumbs, sidebars); register them in the layout contract and document them locally.

## Fragment targets, scopes, and OOB

Registered **fragment targets** (``FragmentTargetRegistry``) map ``HX-Target`` to Kida blocks. Each target may declare a ``scope_name`` tying it to a symbolic scope level.

``triggers_shell_update`` means: "this swap may change shell regions; run shell negotiation (including ``shell_actions`` OOB)." Set it ``False`` for narrow in-page swaps (e.g. ``#page-content-inner``) that should not refresh the topbar.

**Scoped OOB:** When a swap targets a specific scope (e.g. ``page``), layout OOB blocks fire only for layouts at or above that scope's depth — the matched shell and its ancestors, not sibling or descendant shells. Boosted navigation (no explicit ``hx-target``) fires OOB at all levels.

## Contract checks

``app.check()`` validates scope metadata at freeze time:

- **Duplicate swap_scope** per layout chain (two layouts claiming the same scope name)
- **Missing outlet** — ``outlet_target_id`` declared but no ``id="..."`` found in any template
- **Frame/swap conflict** — a ``frame_targets`` id is also registered as a fragment swap target
- **Conflicting outlets** — two layouts at the same depth declare different ``outlet_target_id`` values

## HTMX ordering note

htmx applies the **primary** swap before **out-of-band** fragments. chirp-ui's ``app_shell_layout.html`` includes a small ``htmx:beforeSwap`` handler that clears ``#chirp-shell-actions`` when the response contains a matching OOB, avoiding one frame of stale actions. See chirp-ui app shell docs for details.

## See also

- [App shells](/chirp/docs/guides/app-shell/) — navigation model and ``use_chirp_ui``
- [chirp-ui App Shell](https://lbliii.github.io/chirp-ui/docs/app-shell/) — layouts and components
- [Shell, sections, and route tabs (checklist)](https://github.com/lbliii/chirp-ui/blob/main/docs/SHELL-TABS-CONTRACT.md) — chirp-ui doc: sections, ``TabItem``, ``hx-target``, and OOB handoffs
