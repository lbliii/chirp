---
title: Route Directory Contract
description: Reserved files, inheritance rules, route kinds, and shell contract for filesystem routes
draft: false
weight: 30
lang: en
type: doc
tags: [routing, contracts, filesystem]
keywords: [route contract, _meta.py, _context.py, _actions.py, RouteMeta, sections, route_tabs]
category: reference
---

## Overview

The **route directory contract** defines how Chirp discovers and wires filesystem routes. It specifies reserved files, their scope (inherited vs route-local), and how metadata, context, and layouts combine. Understanding this contract helps you structure route directories correctly and avoid common mistakes.

## Reserved Files

| File | Scope | Purpose |
|------|-------|---------|
| `page.py` | route-local | Primary route handler. Exports `get`, `post`, etc. or `handler`. `page.py` → directory URL; other `.py` files append their stem. |
| `page.html` | route-local | Primary page template. Sibling of `page.py`. Defines fragment blocks. |
| `_meta.py` | route-local | Route metadata (title, section, breadcrumb_label, shell_mode). Exports `META` or `meta()`. |
| `_context.py` | inherited | Subtree-scoped context provider. Exports `context()` receiving path params, parent context, and services. |
| `_layout.html` | inherited | Subtree layout wrapper. Declares `{# target: element_id #}` and `{% block content %}`. |
| `_actions.py` | route-local | Mutation handlers. Exports `@action` decorated functions. |
| `_viewmodel.py` | route-local | View assembly. Exports `viewmodel()` merging data for templates. |

## RouteMeta

`_meta.py` provides route metadata via a static `META` constant or a `meta()` callable:

```python
from chirp.pages.types import RouteMeta

META = RouteMeta(
    title="Skills",
    section="discover",
    breadcrumb_label="Skills",
    shell_mode="tabbed",
)
```

Or dynamically:

```python
def meta(name: str) -> RouteMeta:
    return RouteMeta(title=f"Skill: {name}", breadcrumb_label=name)
```

**Fields:** `title`, `section`, `breadcrumb_label`, `shell_mode`, `auth`, `cache`, `tags`.

## Sections

Register sections before `mount_pages()`:

```python
from chirp.pages.types import Section, TabItem

app.register_section(Section(
    id="discover",
    label="Discover",
    tab_items=(TabItem(label="Skills", href="/skills"),),
    breadcrumb_prefix=({"label": "App", "href": "/"},),
))
```

Routes bind to sections via `RouteMeta.section`. The framework resolves `tab_items` and `breadcrumb_prefix` from the matched section. Tab rows use the same data under **`route_tabs`** (an alias of `tab_items`) for chirp-ui’s `render_route_tabs` macro. Each item is a dict shaped like `TabItem`: `label`, `href`, optional `icon`, `badge`, and optional `match` (`"exact"` or `"prefix"` for nested URLs).

For delivery modes (`hx-target`, boost vs route-tab clicks) and a full checklist, see the [shell, sections, and route tabs contract](https://github.com/lbliii/chirp-ui/blob/main/docs/SHELL-TABS-CONTRACT.md) in the chirp-ui repository.

## Context Cascade

`_context.py` providers run root-first. Each receives path params, accumulated parent context, and service providers. Child output overrides parent. `shell_actions` merges deeply.

## Layout Chain

Layouts inherit down the directory tree. Each `_layout.html` declares `{# target: element_id #}`. Render depth depends on `HX-Target`: full page renders all; fragment requests start at the matching layout.

## Shell Context Assembly

The framework provides: `page_title`, `breadcrumb_items`, `tab_items`, `route_tabs` (same list as `tab_items` when the section defines tabs), `current_path`. Resolution order: `RouteMeta` → section → handler override.

**Imperative routes:** For handlers that return `Template(...)` or `Page(...)` directly (not using filesystem routing), Chirp auto-injects `current_path = request.path` into the template context when the handler does not provide it. This ensures ChirpUI navigation macros with `match=` work for both filesystem and imperative route styles.

## Route Kinds

| Kind | Files | Description |
|------|-------|-------------|
| page | page.py, page.html | Standard page with template |
| detail | page.py, page.html in `{param}/` | Parametrized page |
| action | page.py (no template) | Mutation-only route |
| redirect | page.py returning Redirect | Redirect route |

## Actions

`_actions.py` exports `@action` decorated handlers. Forms use `_action` field to dispatch. The framework discovers actions at route registration.

## Viewmodel

`_viewmodel.py` exports `viewmodel()` for complex view assembly. Its output merges after cascade and shell context.

## Contract Validation

`app.check()` validates route contracts: section bindings, shell mode/block alignment, route file consistency, duplicate routes, section tab hrefs, and context provider signatures.

## Introspection

When `config.debug=True`:

- **Debug headers**: `X-Chirp-Route-Kind`, `X-Chirp-Route-Files`, `X-Chirp-Route-Meta`, `X-Chirp-Route-Section`, `X-Chirp-Context-Chain`, `X-Chirp-Shell-Context`
- **Route explorer**: `GET /__chirp/routes` shows the full route tree with drill-down
- **HTMX panel**: Activity log entries show route metadata when expanded
