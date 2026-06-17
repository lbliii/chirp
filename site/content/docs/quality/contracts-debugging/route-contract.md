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

When you build pages with [[docs/build-apps/pages-navigation/filesystem-routing|filesystem routing]], Chirp discovers routes from files on disk — `page.py` handlers, `page.html` templates, and reserved underscore files like `_meta.py` and `_context.py`. The **route directory contract** is the set of rules for those files: which ones Chirp looks for, whether each is scoped to one route or inherited down the tree, and how their metadata, context, and layouts combine.

Reach for this page when you are laying out a route directory and need to know what each reserved file does, or when `app.check()` flags a route-contract issue you want to fix.

:::{note}
This contract applies only to filesystem-routed pages. Handlers you register imperatively with `@app.route(...)` follow [[docs/build-apps/pages-navigation/routes|the route handler rules]] instead — they do not use `_meta.py`, `_context.py`, or layout chains.
:::

## Reserved Files

Every file Chirp recognizes in a route directory, what it does, and whether it is scoped to one route or inherited by every route below it:

:::{list-table}
:header-rows: 1

* - File
  - Scope
  - Purpose
* - `page.py`
  - route-local
  - Primary route handler. Exports `get`, `post`, etc. (or a `handler` fallback). `page.py` maps to the directory URL; any other `.py` file appends its stem.
* - `page.html`
  - route-local
  - Primary page template, sibling of `page.py`. Defines the fragment blocks rendered into the layout.
* - `_meta.py`
  - route-local
  - Route metadata — title, section, breadcrumb label, shell mode. Exports a `META` constant or a `meta()` callable.
* - `_context.py`
  - inherited
  - Subtree-scoped context provider. Exports `context()`, which receives path params, parent context, and services.
* - `_layout.html`
  - inherited
  - Subtree layout wrapper. Declares `{# target: element_id #}` and a `{% block content %}` the page composes into.
* - `_actions.py`
  - route-local
  - Mutation handlers. Exports `@action`-decorated functions dispatched by an `_action` form field.
* - `_viewmodel.py`
  - route-local
  - View assembly. Exports `viewmodel()` to merge data for the template.
:::

## Minimal working example

A route directory needs only two files to serve a titled page: a `page.py` handler and a sibling `_meta.py`.

:::{example}
A `projects/` route that renders a fragment into the app shell and carries a breadcrumb:

```python
# pages/projects/page.py
from chirp import Page


def get(projects: tuple[dict[str, str], ...]) -> Page:
    return Page(
        "projects/page.html",
        "page_content",
        page_block_name="page_root",
        projects=projects,
    )
```

```python
# pages/projects/_meta.py
from chirp.pages.types import RouteMeta

META = RouteMeta(title="Projects", breadcrumb_label="Projects")
```

The handler returns a `Page` so Chirp sends a fragment to htmx and a full page to a browser. The `RouteMeta` supplies the title and breadcrumb that the app shell renders around it.
:::

*Source: [`examples/chirpui/pages_shell/pages/projects`](https://github.com/lbliii/chirp/blob/main/examples/chirpui/pages_shell/pages/projects/page.py).*

For dynamic metadata, export a `meta()` callable instead of the `META` constant — it receives path params:

```python
# pages/projects/{slug}/_meta.py
from chirp.pages.types import RouteMeta


def meta(slug: str) -> RouteMeta:
    return RouteMeta(title=f"Project: {slug}", breadcrumb_label=slug)
```

`RouteMeta` is a frozen dataclass; every field is optional:

| Field | Type | What it sets |
|---|---|---|
| `title` | `str` | Page title (`page_title` in shell context) |
| `section` | `str` | Binds the route to a registered `Section` for tabs and breadcrumbs |
| `breadcrumb_label` | `str` | This route's breadcrumb segment |
| `shell_mode` | `str` | App-shell mode (e.g. `"tabbed"`) |
| `auth` | `str` | Auth tag for the route |
| `cache` | `str` | Cache policy tag |
| `tags` | `tuple[str, ...]` | Free-form tags |

## Sections

A `Section` groups routes under shared navigation — tabs and a breadcrumb prefix. Register sections before `mount_pages()`:

```python
from chirp.pages.types import Section, TabItem

app.register_section(Section(
    id="discover",
    label="Discover",
    tab_items=(TabItem(label="Skills", href="/skills"),),
    breadcrumb_prefix=({"label": "App", "href": "/"},),
))
```

A route joins a section by setting `RouteMeta.section` to the section `id`. Chirp then resolves the section's `tab_items` and `breadcrumb_prefix` into the shell context for that route. The same tab list is exposed under **`route_tabs`** for chirp-ui's `render_route_tabs` macro. Each `TabItem` carries a `label`, `href`, optional `icon` and `badge`, and a `match` mode (`"exact"` or `"prefix"`) that controls active state for nested URLs.

:::{note} See also
- [[docs/build-apps/pages-navigation/route-directory|Route directory layout]] — the full file-by-file walkthrough.
- The [shell, sections, and route-tabs contract](https://github.com/lbliii/chirp-ui/blob/main/docs/SHELL-TABS-CONTRACT.md) in the chirp-ui repo — delivery modes (`hx-target`, boost vs route-tab clicks) and the full checklist.
:::

## Route Kinds

Chirp classifies each discovered route by the files it finds:

:::{list-table}
:header-rows: 1

* - Kind
  - Files
  - Description
* - `page`
  - `page.py` + `page.html`
  - Standard page with a template.
* - `detail`
  - `page.py` + `page.html` inside `{param}/`
  - Parametrized page.
* - `action`
  - `page.py` (no template)
  - Mutation-only route.
* - `redirect`
  - `page.py` returning a `Redirect`
  - Redirect route.
:::

## Actions

`_actions.py` exports `@action`-decorated handlers. The decorator takes the name a form uses to target it:

```python
from chirp.pages.actions import action
from chirp import OOB, Fragment


@action("rename")
def rename(name: str) -> OOB:
    # ... update data ...
    return OOB(Fragment("page.html", "title", title=name))
```

A form selects the action with an `_action` field whose value matches the decorator name:

```html
<form hx-post="" hx-target="#title">
  <input type="hidden" name="_action" value="rename">
  <input name="name">
  <button>Save</button>
</form>
```

Chirp discovers actions at route registration and dispatches by the `_action` value.

## Contract validation

`app.check()` validates the route directory contract at startup. Read each issue
as a pointer to one concrete fix target: a useful diagnostic names the route,
template, block, selector, middleware, config flag, import string, or
registration that must change. The route-specific categories:

| Category | Severity | What it catches |
|----------|----------|-----------------|
| `route_contract` | ERROR / WARNING | Umbrella for section bindings, shell-mode/block alignment, route-file consistency, duplicate routes, section tab hrefs, and `_context.py` provider signatures. |
| `page_handlers` | ERROR / WARNING | A `page.py` defines no recognized HTTP method handler. A handler-shaped typo (`def handle`, `def GET`) is a WARNING; an entirely missing handler is an ERROR, because the file would register no routes. |
| `route_names` | ERROR | Two routes at *different* paths claim the same name, so `app.url_for(name)` would resolve ambiguously. Method variants of the same URL are not flagged. |
| `mount_app_merge` | INFO | `app.mount_app()` dropped a sub-app global, filter, provider, handler, or severity override because the parent had already registered one. Parent-wins is intentional. |
| `hx-target` | ERROR / WARNING | htmx attributes (`hx-target`, `hx-indicator`, `hx-boost`) reference a missing selector or an unsafe target. Fix the selector or element named in the issue. |
| `csrf_form` | WARNING | `CSRFMiddleware` is active and a static mutating `<form>` has no `{{ csrf_field() }}`, `csrf_token()`, or `_csrf_token` field. |
| `dead` | WARNING | A template exists but no route, include, import, or layout references it — usually cleanup, not a deploy blocker. |

Each category is a stable handle for CI policy; the message names the concrete fix target. Tune any category before running checks:

```python
from chirp.contracts.types import Severity

# Demote the missing-handler ERROR during a migration:
app.override_contract_severity("page_handlers", Severity.WARNING)
```

:::{note} See also
- [[docs/quality/contracts-debugging/categories|Contract Category Reference]] — every `app.check()` category, default severity, and fix target. The route checks above are a subset.
- [[docs/quality/contracts-debugging/debugging-swaps|Debugging Swaps]] — when the contract passes but htmx swaps the wrong thing in the browser.
:::

## Advanced and introspection

:::{dropdown} How layouts and context resolve
**Context cascade.** `_context.py` providers run root-first. Each receives path params, the accumulated parent context, and service providers. Child output overrides parent values; `shell_actions` merges deeply.

**Layout chain.** Layouts inherit down the directory tree. Each `_layout.html` declares `{# target: element_id #}` — the DOM node it fills in a nested chain — and an optional `{# outlet: element_id #}` for the primary boosted-navigation outlet (for example `main` in a chirp-ui app shell). `LayoutChain.find_start_index_for_target` matches both, so a boosted `HX-Target` header can hit `#main` while the layout's own `target` stays `body`. Render depth depends on `HX-Target`: a full page renders every layout; a boosted request starts at the matching layout. See [[docs/build-apps/html-fragments/layout-patterns|Layout patterns]].

**Shell context.** Chirp assembles `page_title`, `breadcrumb_items`, `tab_items`, `route_tabs`, and `current_path` from `RouteMeta`, then the section, then any handler override — in that order. For imperative handlers that return `Template(...)` or `Page(...)` directly, Chirp injects `current_path = request.path` when the handler does not provide it, so chirp-ui navigation macros with `match=` work for both routing styles.

**Viewmodel.** `_viewmodel.py` exports `viewmodel()` for complex view assembly. Its output merges after the context cascade and shell context.
:::

:::{dropdown} Introspection (debug mode only)
When `config.debug=True`, Chirp exposes route diagnostics:

- **Debug headers** on every response: `X-Chirp-Route-Kind`, `X-Chirp-Route-Files`, `X-Chirp-Route-Meta`, `X-Chirp-Route-Section`, `X-Chirp-Context-Chain`, `X-Chirp-Shell-Context`.
- **Route explorer**: `GET /__chirp/routes` renders the full route tree with drill-down into layouts, providers, actions, and metadata.
- **HTMX panel**: activity-log entries show route metadata when expanded.

For htmx request records and Swap Doctor diagnostics, open Chirp DevTools with `Ctrl+Shift+D` in debug mode.
:::

:::{note} See also
- [[docs/build-apps/pages-navigation/filesystem-routing|Filesystem routing]] — how Chirp discovers and wires routes from disk.
- [[docs/build-apps/pages-navigation/request-response|Request and response]] — what a handler receives and returns.
:::
