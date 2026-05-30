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
| `_layout.html` | inherited | Subtree layout wrapper. Declares `{# target: element_id #}` (and optionally `{# outlet: element_id #}`, `{# swap_scope: #}`, `{# frames: #}`) and `{% block content %}`. |
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

Layouts inherit down the directory tree. Each `_layout.html` declares `{# target: element_id #}` (which DOM node the layout fills in a nested chain). Optional `{# outlet: element_id #}` declares the **primary navigation outlet** (for example `main` for chirp-ui app shells). `LayoutChain.find_start_index_for_target` matches **both** so boosted `HX-Target` headers can target `#main` while the layout’s `target` remains `body`. Render depth depends on `HX-Target`: full page renders all layouts; boosted requests start at the matching layout. See [[docs/build-apps/pages-navigation/filesystem-routing|Filesystem routing]] (persistent app shell pattern).

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

Beyond route-level checks, `app.check()` also validates hypermedia surface
contracts. The table below is a category reference for the checks users most
often tune in CI:

For the full category list, default severity, and fix target guidance, see
[[docs/quality/contracts-debugging/categories|Contract Category Reference]].

Read each issue as a pointer to one concrete fix target. A useful diagnostic
names the route, template, block, selector, middleware, config flag, import string,
or registration that must change. Terminal output groups categories by concern
(`Routing`, `HTMX`, `Forms`, `OOB / Suspense / SSE`, and so on) so the first
header tells you which surface to inspect before you open the file.

| Check | Severity | What it catches |
|---|---|---|
| `page_handlers` | ERROR / WARNING | `page.py` defines no recognised HTTP method handler (`get`/`post`/… or `handler` fallback). Handler-shaped typos (`def handle`, `def GET`, `def index`) emit WARNING; an entirely missing handler emits ERROR — the file would register no routes and requests 404/500 at runtime. |
| `route_names` | ERROR | Two routes at *different* paths claim the same name — `app.url_for(name)` would ambiguously resolve. Method variants of the same URL (e.g. GET from `page.py` + POST from `_actions.py`) are *not* flagged. Fix by renaming one of the pages or setting a module-level `name = "…"` override. |
| `mount_app_merge` | INFO | `app.mount_app(prefix, sub_app)` dropped a sub-app template global, filter, provider, error handler, or severity override because the parent had already registered one. Parent-wins is intentional; promote via `override_contract_severity("mount_app_merge", Severity.WARNING)` if you want CI to flag them. |
| `dead` | INFO | A template exists in the template directory but no route, include, import, or layout references it. Usually cleanup, not a deploy blocker. |
| `component` | ERROR | Component-call validation surfaced by Kida/chirp-ui metadata. The Chirp adapter is wired; full precision depends on typed component metadata from the template package. |
| `unreachable_block` | WARNING | A filesystem page template defines a sibling block that layout composition will never render, such as `page_scripts` outside `page_content`. Move the content inside the rendered page block or make it a real fragment target. |
| `composition_extends` | WARNING | A page template extends a registered layout instead of composing into it. Pages should render into the layout content block via `render_with_blocks`; they should not override sibling layout blocks. |
| `hx-target`, `hx-indicator`, `hx-boost` | ERROR / WARNING | htmx attributes reference missing selectors, invalid boosted links, or unsafe targets. Fix the selector or target element named in the issue. |
| `fragment_target_orphan` | ERROR / WARNING | A required fragment target registry entry points at a block no template provides, or an optional entry cannot be resolved. Required entries are errors because htmx would otherwise swap nothing. |
| `fragment_target_scan` | ERROR | Chirp could not inspect a page template while checking fragment target registrations. Fix the named template parse/load error first; otherwise orphaned target checks may be incomplete. |
| `oob_registry` | ERROR / WARNING | A registered OOB region references a missing block or mismatched target. Required missing regions fail startup; optional regions can be warnings. |
| `reactive_block` | ERROR | `DependencyIndex` block reference points to a non-existent template block (typo or renamed block) |
| `reactive_cycle` | WARNING | Derivation graph contains a cycle (`index.derive()` forms a loop) |
| `reactive_paths` | WARNING | A declared `ChangeEvent.changed_paths` value is not registered in the `DependencyIndex`; the event will not update any block. |
| `reactive_audience` | WARNING | A scope declares audience-filtered events but no connection-aware `reactive_stream(..., connection=ConnectionInfo(...))`. |
| `oob_target` | WARNING | `hx-swap-oob` element references an `id` not found in any template |
| `fragment_scope` | WARNING | A nested fragment block references an import or binding defined only inside an ancestor block; direct `render_block()` or block-fetch rendering skips that ancestor scope |
| `sse_self_swap` | ERROR | `sse-connect` and `sse-swap` appear on the same element. Put `sse-swap` on a child sink so htmx can target the update correctly. |
| `sse_scope` | ERROR | An SSE connection sits inside a broad inherited htmx target without `hx-disinherit` or another safe scope boundary. |
| `sse_crossref` | ERROR / INFO | `sse-swap="name"` listens for an event no route declares or infers, or a route emits an event no template listens for. |
| `defer_falsy` | WARNING | A Suspense template checks a deferred key with bare truthiness (`{% if key %}`), which keeps skeletons visible for empty lists, empty strings, or `0`. Use `{% if key is deferred %}` or `"key" in __chirp_defer_pending__` to distinguish loading from loaded before testing resolved values. |
| `alpine_cdn_url` | ERROR | A bare jsDelivr Alpine URL would load the package CommonJS entry instead of the browser CDN build. Use `/dist/cdn.min.js`. |
| `form` | ERROR / WARNING | A route form contract and the template's actual `<input>`, `<select>`, or `<textarea>` names disagree. |
| `form_contract` | INFO | `<form action="/path" method="post">` targets a route with no `FormContract` declaration |
| `csrf_form` | WARNING | `CSRFMiddleware` is active and a static mutating `<form>` has no `{{ csrf_field() }}`, `csrf_token()`, or `_csrf_token` field. |
| `a11y_label`, `a11y_alt`, `a11y_heading`, `a11y_landmark` | WARNING | Accessibility checks for missing labels, missing image alt text, skipped heading levels, or missing landmarks. |
| `csrf_session`, `secret_key`, `middleware_signature` | ERROR / WARNING | Production-safety checks for security middleware ordering, missing secret keys, and middleware call signatures. |

These checks run automatically as part of `chirp check myapp:app`. Some
categories only activate when the app provides the relevant metadata, such as a
`DependencyIndex`, `FormContract`, OOB registry entries, or docs plugin
collection.

`app.check()` is not a style linter. It exists to catch wiring that can make
the browser swap the wrong thing, silently skip an OOB update, or route a page
into the wrong shell. For visual symptoms and browser-side diagnostics, start
with [[docs/quality/contracts-debugging/debugging-swaps|Debugging Swaps]].

Any category can be tuned with `app.override_contract_severity()` — for example,
demote the missing-handler ERROR during a migration:

```python
from chirp.contracts.types import Severity

app.override_contract_severity("page_handlers", Severity.WARNING)
```

## Introspection

When `config.debug=True`:

- **Debug headers**: `X-Chirp-Route-Kind`, `X-Chirp-Route-Files`, `X-Chirp-Route-Meta`, `X-Chirp-Route-Section`, `X-Chirp-Context-Chain`, `X-Chirp-Shell-Context`
- **Route explorer**: `GET /__chirp/routes` shows the full route tree with drill-down
- **HTMX panel**: Activity log entries show route metadata when expanded

For htmx request records and Swap Doctor diagnostics, open Chirp DevTools with
`Ctrl+Shift+D` in debug mode.
