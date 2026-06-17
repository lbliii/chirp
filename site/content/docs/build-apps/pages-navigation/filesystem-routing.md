---
title: Filesystem Routing
description: Build routes from a pages/ directory — folders become URLs, page.py files become handlers, and _context.py shares data down the tree
draft: false
weight: 15
lang: en
type: doc
tags: [routing, pages, filesystem, context]
keywords: [mount_pages, page.py, _layout.html, _context.py, discover_pages]
category: guide
---

## Overview

Filesystem routing builds your routes from a `pages/` directory instead of `@app.route()` calls. The folder structure *is* the URL structure: a `page.py` file becomes a GET handler for its directory's path, `{braces}` folders become path parameters, and `_context.py` files share data down the tree.

Reach for it when your app is a content hierarchy — docs, a forum, a dashboard with nested sections — and you want handlers, templates, and shared data co-located with the URLs they serve. For API-style or action endpoints, keep using [[docs/build-apps/pages-navigation/routes|decorator routes]]. You can mix both in one app.

```python
from chirp import App, AppConfig

app = App(AppConfig(template_dir="pages"))
app.mount_pages("pages")
app.run()
```

## Directory conventions

The discovery system walks the `pages/` directory and treats specific files as route definitions:

:::{list-table}
:header-rows: 1

* - File
  - Purpose
* - `page.py`
  - GET handler for the directory's URL (`documents/page.py` → `GET /documents`).
* - `edit.py`, `create.py`, …
  - Handlers that append the filename to the path (`edit.py` → `GET /documents/edit`).
* - `_context.py`
  - Context provider that cascades to child routes.
* - `_layout.html`
  - Layout shell the page renders into.
* - `_actions.py`
  - Mutation handlers declared with the `@action` decorator.
* - `_meta.py`
  - Route metadata (title, section, breadcrumb label).
* - `_viewmodel.py`
  - View assembly for complex context merging.
:::

Directories whose names are wrapped in `{braces}` become path parameters (`{doc_id}/` → `/documents/{doc_id}`).

:::{note} See also
- [[docs/build-apps/pages-navigation/route-directory|Route Directory Golden Path]] — recommended patterns for laying out a `pages/` tree
- [[docs/quality/contracts-debugging/route-contract|Route Directory Contract]] — the full reserved-file vocabulary and the startup checks that enforce it
:::

## Example structure

```text
pages/
  _layout.html          # Root layout
  _context.py           # Root context (e.g. site config)
  documents/
    page.py             # GET /documents
    create.py           # GET /documents/create
    {doc_id}/
      _layout.html      # Nested layout
      _context.py       # Loads the doc, provides it to children
      page.py           # GET /documents/{doc_id}
      page.html         # Template for page.py
      edit.py           # GET /documents/{doc_id}/edit
      edit.html         # Template for edit.py
```

A request resolves through the tree in a fixed order:

::::{steps}
:::{step} Discovery maps the URL to a route file
`mount_pages()` walks `pages/` once at startup. The matching `page.py` (or other handler file) for the requested path is selected, along with its ancestor `_context.py` and `_layout.html` files.
:::{/step}
:::{step} Context cascades root to leaf
Each `_context.py` provider runs in order. Output merges into an accumulated dict; deeper providers override parent values.
:::{/step}
:::{step} The handler runs with resolved kwargs
The `get`/`post`/… function receives path params, cascade context, and services as keyword arguments, then returns a [[docs/about/core-concepts/return-values|Page]] (or any other return type).
:::{/step}
:::{step} The layout chain wraps the result
Chirp composes the ancestor layouts around the page HTML. See [[docs/build-apps/html-fragments/layout-patterns|layout composition]] for how that wrapping works.
:::{/step}
::::{/steps}

## Route files

### page.py

`page.py` maps to the **directory URL**. A `get` function handles `GET`, a `post` function handles `POST`, and so on:

```python
# pages/documents/page.py
from chirp import Page

def get():
    return Page("documents/page.html", "content", items=load_items())
```

You can also return `Suspense` for instant first paint with deferred blocks — see [[docs/build-apps/streaming-updates/_index|Suspense for instant first paint]]. The layout chain applies automatically.

### Other .py files

Any other `.py` file (except names starting with `_`) appends its stem to the path:

- `edit.py` in `documents/{doc_id}/` → `GET /documents/{doc_id}/edit`
- `create.py` in `documents/` → `GET /documents/create`

Handler functions are named after HTTP methods: `get`, `post`, `put`, `delete`, `patch`, `head`, `options`. If no method-named function exists, a `handler` function defaults to GET.

A file can mix methods — a sync `get` for the form and an async `post` for the mutation:

::::{code-tabs}
:sync: handler

```python
# pages/documents/{doc_id}/edit.py — GET handler
from chirp import Page

def get(doc_id: str, doc):  # doc comes from _context.py
    return Page("documents/{doc_id}/edit.html", "content", doc=doc)
```

```python
# pages/documents/{doc_id}/edit.py — POST handler
from chirp import Redirect

async def post(doc_id: str, doc, request):
    data = await request.form()
    update_doc(doc_id, data)
    return Redirect(f"/documents/{doc_id}")
```

::::

## Path parameters

Directory names wrapped in `{param}` become URL path parameters:

```text
documents/{doc_id}/page.py             →  /documents/{doc_id}
users/{user_id}/posts/{slug}/page.py   →  /users/{user_id}/posts/{slug}
```

Handlers receive path parameters as keyword arguments by name. Directory names are bare `{braces}` — the type comes from the handler's parameter annotation. Annotate `doc_id: int` and the matched segment is coerced to `int` before the handler runs.

## Context cascade

`_context.py` files export a `context` function that provides shared data to handlers. Context cascades from root to leaf; child context overrides parent.

A provider receives arguments from two sources:

1. **Path parameters** — from the URL match (e.g. `doc_id` from `/documents/{doc_id}`).
2. **Parent context** — values from providers higher in the tree.

```python
# pages/_context.py — root provider, no params
def context() -> dict:
    return {"store": get_store(), "data_dir": "..."}

# pages/documents/{doc_id}/_context.py — receives doc_id from the path, store from the parent
def context(doc_id: str, store) -> dict:
    doc = store.get(doc_id)
    return {"doc": doc}
```

For `/documents/abc-123`, the root provider runs first and adds `store` and `data_dir`. The child provider then receives `doc_id="abc-123"` from the path and `store` from the accumulated context. Providers can be sync or async.

### Inject services by type

A provider can also request types registered via `app.provide()`. A parameter whose type annotation matches a registered factory is resolved from that factory:

```python
# pages/documents/{doc_id}/_context.py
def context(doc_id: str, store: DocumentStore) -> dict:
    doc = store.get(doc_id)
    return {"doc": doc}
```

With `app.provide(DocumentStore, get_store)`, the `store` parameter is injected from the factory.

### Abort the cascade with an HTTPError

A provider can raise `NotFound` (or any other `HTTPError` subclass) to stop the cascade. Chirp renders the matching error page automatically:

```python
# pages/documents/{doc_id}/_context.py
from chirp import NotFound

def context(doc_id: str, store) -> dict:
    doc = store.get(doc_id)
    if doc is None:
        raise NotFound(f"Document '{doc_id}' not found")
    return {"doc": doc}
```

:::{dropdown} Advanced: route-scoped shell actions
:icon: layers

`_context.py` can return a reserved `shell_actions` value to drive persistent shell chrome such as a global top bar. Shell actions cascade root-to-leaf like other context, but they merge by stable action `id` rather than dict overwrite — child routes inherit parent actions, override one by `id`, remove one by `id`, or `replace` the inherited set entirely.

```python
from chirp import ShellAction, ShellActions, ShellActionZone

# pages/forum/_context.py
def context() -> dict:
    return {
        "shell_actions": ShellActions(
            primary=ShellActionZone(
                items=(
                    ShellAction(id="new-thread", label="New thread", href="/forum/new"),
                )
            )
        )
    }

# pages/forum/{thread_id}/_context.py
def context(thread_id: str) -> dict:
    return {
        "shell_actions": ShellActions(
            primary=ShellActionZone(
                items=(
                    ShellAction(id="reply", label="Reply", href=f"/forum/{thread_id}/reply"),
                ),
                remove=("new-thread",),
            )
        )
    }
```

The resolved `shell_actions` object is available in page and layout templates. For boosted shell navigations, Chirp emits an out-of-band refresh for the default target `#chirp-shell-actions` so persistent top bars stay in sync as the route changes.
:::

## Templates

When a route file has a sibling `.html` file with the same stem, you render it by passing its path to `Page()`. Template paths are relative to the pages root:

- `page.py` + `page.html` → `return Page("documents/page.html", "content", ...)`
- `edit.py` + `edit.html` → `return Page("documents/edit.html", "content", ...)`

The page template owns the region inside the layout's `{% block content %}`. It does **not** `{% extends %}` its sibling `_layout.html` — Chirp composes them. That distinction (and why a page can't fill a layout block like `page_scripts`) is the subject of [[docs/build-apps/html-fragments/layout-patterns|layout composition]].

:::{dropdown} Advanced: render scopes for boosted navigation
:icon: layers

For layout-heavy pages, give the page two render scopes — a narrow fragment block for explicit swaps and a wider page-level block for boosted navigation:

```html
{# pages/_page_layout.html #}
{% block content %}
{% block page_root %}
  <div class="page-shell">
    {% block page_header %}{% end %}
    {% block page_content %}{% end %}
  </div>
{% endblock %}
{% endblock %}
```

```python
return Page(
    "documents/page.html",
    "page_content",        # narrow fragment swap target
    page_block_name="page_root",  # wider root for boosted navigation
    items=load_items(),
)
```

`page_content` renders for explicit fragment swaps into a narrow target; `page_root` renders for boosted navigation, where the response must carry page-level wrappers such as toolbars and spacing.
:::

## Handler argument resolution

Page handlers receive arguments from several sources, in priority order — first match wins:

:::{dropdown} Request
:icon: arrow-right

`request: Request` by parameter name or type annotation. Injected when the handler has a parameter named `request` or annotated with `Request`.
:::

:::{dropdown} Path parameters
:icon: link

From the URL match, with type coercion. Parameters like `{doc_id}` are extracted and passed by name; annotate `doc_id: int` to coerce.
:::

:::{dropdown} Cascade context
:icon: layers

From `_context.py` providers. Each provider's output merges into the accumulated context; deeper providers override parent values.
:::

:::{dropdown} Service providers
:icon: package

Registered via `app.provide()`. When a parameter's type matches a registered annotation, Chirp calls the factory and injects the result.
:::

:::{dropdown} Extractable dataclasses
:icon: database

From the query string (GET) or form/JSON body (POST). Dataclasses with appropriate annotations are populated from the request data.
:::

```python
def get(doc_id: str, doc, store: DocumentStore):
    # doc_id from path, doc from _context.py, store from app.provide()
    return Page("documents/page.html", "content", doc=doc)
```

## Gotchas

:::{warning}
Non-root `_layout.html` files default their target to `body` when no `{# target: element_id #}` comment is declared. A missing target on an inner layout collapses the layout chain and breaks boosted navigation. Declare a unique target on each non-root layout. See [[docs/build-apps/html-fragments/layout-patterns|layout composition]] for the full target/outlet mechanics.
:::

## Filesystem vs decorator routes

:::{list-table}
:header-rows: 1

* - Use filesystem routing when…
  - Use `@app.route()` when…
* - Routes map to a content hierarchy
  - Routes are API-like or action-oriented
* - Layouts and context cascade naturally
  - Each route is independent
* - You want co-located handlers and templates
  - You prefer explicit route registration
:::

You can mix both: `app.mount_pages("pages")` for the main app, and `@app.route("/api/...")` for API endpoints.

## See also

:::{note} See also
- [[docs/build-apps/pages-navigation/routes|Routes]] — decorator-based route registration
- [[docs/build-apps/html-fragments/layout-patterns|Layout Patterns]] — how page HTML composes into a `_layout.html` shell
- [[docs/about/core-concepts/return-values|Return Values]] — what `Page` and the other return types do
- [[docs/build-apps/html-fragments/fragments|Fragments]] — block-level rendering for htmx
- [[docs/tutorials/view-transitions-oob|View Transitions]] — boosted navigation with layouts
:::
