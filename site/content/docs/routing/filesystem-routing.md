---
title: Filesystem Routing
description: Route discovery from the pages/ directory with layouts and context cascade
draft: false
weight: 15
lang: en
type: doc
tags: [routing, pages, filesystem, layouts, context]
keywords: [mount_pages, page.py, _layout.html, _context.py, discover_pages]
category: guide
---

## Overview

Chirp can discover routes from a **pages directory** instead of registering them with `@app.route()`. The filesystem structure defines URL paths, layout nesting, and shared context. This is ideal for content-heavy apps where routes map naturally to a directory tree.

```python
from chirp import App, AppConfig

app = App(AppConfig(template_dir="pages"))
app.mount_pages("pages")
app.run()
```

## Directory Conventions

The discovery system walks the `pages/` directory and treats specific files as route definitions:

| File | Purpose |
|------|---------|
| `page.py` | Route handler for the directory URL (e.g. `documents/page.py` → `GET /documents`) |
| `edit.py`, `create.py`, etc. | Route handlers that append to the path (e.g. `edit.py` → `GET /documents/edit`) |
| `_layout.html` | Layout shell with `{% block content %}` and `{# target: element_id #}` |
| `_context.py` | Context provider that cascades to child routes |

Directories whose names are wrapped in `{braces}` become path parameters (e.g. `{doc_id}/` → `/documents/{doc_id}`).

## Example Structure

```text
pages/
  _layout.html          # Root layout (target: body)
  _context.py           # Root context (e.g. site config)
  documents/
    page.py             # GET /documents
    create.py           # GET /documents/create
    {doc_id}/
      _layout.html      # Nested layout (target: app-content)
      _context.py       # Loads doc, provides to children
      page.py           # GET /documents/{doc_id}
      page.html         # Template for page.py
      edit.py           # GET /documents/{doc_id}/edit
      edit.html         # Template for edit.py
```

## Route Files

### page.py

`page.py` maps to the **directory URL**. A `get` function handles `GET`, a `post` function handles `POST`, etc.

```python
# pages/documents/page.py
from chirp import Page

def get():
    return Page("documents/page.html", "content", items=load_items())
```

### Other .py Files

Any other `.py` file (except those starting with `_`) appends its stem to the path:

- `edit.py` in `documents/{doc_id}/` → `GET /documents/{doc_id}/edit`
- `create.py` in `documents/` → `GET /documents/create`

Handler functions are named after HTTP methods: `get`, `post`, `put`, `delete`, `patch`, `head`, `options`. If no method-named function exists, a `handler` function defaults to GET.

```python
# pages/documents/{doc_id}/edit.py
from chirp import Page, NotFound

def get(doc_id: str, doc):  # doc from _context.py
    return Page("documents/{doc_id}/edit.html", "content", doc=doc)

async def post(doc_id: str, doc, request):
    data = await request.form()
    update_doc(doc_id, data)
    return Redirect(f"/documents/{doc_id}")
```

## Path Parameters

Directory names wrapped in `{param}` become URL path parameters:

```text
documents/{doc_id}/page.py   →  /documents/{doc_id}
users/{user_id}/posts/{slug}/page.py  →  /users/{user_id}/posts/{slug}
```

Handlers receive path parameters as keyword arguments. Type annotations are respected (e.g. `doc_id: int` for `{doc_id:int}`).

## Layouts

Each `_layout.html` defines a shell with a `{% block content %}` slot. The layout declares which DOM element it owns via a target comment:

```html
{# target: body #}
<body hx-boost="true" hx-target="#app-content">
  {% block content %}{% endblock %}
</body>
```

```html
{# target: app-content #}
<div id="app-content">
  {% block content %}{% endblock %}
</div>
```

Layouts nest from root to leaf. The negotiation layer uses `HX-Target` to decide how deep to render:

- **Full page load**: all layouts nested
- **Boosted navigation** with `HX-Target: #app-content`: render from the layout that owns `app-content` down
- **Fragment request**: render just the targeted block

If no target is declared, it defaults to `"body"`.

## Context Cascade

`_context.py` files export a `context` function that provides shared data to handlers. Context cascades from root to leaf; child context overrides parent.

```python
# pages/documents/{doc_id}/_context.py
from chirp import NotFound

def context(doc_id: str) -> dict:
    doc = store.get(doc_id)
    if doc is None:
        raise NotFound(f"Document {doc_id} not found")
    return {"doc": doc}
```

Handlers receive context as keyword arguments. Providers can be sync or async. Raising `NotFound` (or other `HTTPError` subclasses) aborts the cascade and returns the appropriate error response.

## Template Convention

When a route file has a sibling `.html` file with the same stem, that template is used implicitly:

- `page.py` + `page.html` → handler returns `Page("path/to/page.html", "content", ...)`
- `edit.py` + `edit.html` → handler returns `Page("path/to/edit.html", "content", ...)`

Template paths are relative to the pages root. The handler must pass the correct path to `Page()`.

## Handler Argument Resolution

Page handlers receive arguments from multiple sources, in priority order (first match wins):

:::{dropdown} Request
:icon: arrow-right

`request: Request` by parameter name or type annotation. Injected when the handler has a parameter named `request` or annotated with `Request`.
:::

:::{dropdown} Path parameters
:icon: link

From the URL match, with type coercion. Parameters like `{doc_id}` in the route path are extracted and passed by name. Add `:int` or `:float` for automatic conversion.
:::

:::{dropdown} Cascade context
:icon: layers

From `_context.py` providers. Each provider's output is merged into the accumulated context; deeper providers override parent values.
:::

:::{dropdown} Service providers
:icon: package

Registered via `app.provide()`. When a parameter's type matches a registered annotation, Chirp calls the factory and injects the result.
:::

:::{dropdown} Extractable dataclasses
:icon: database

From query string (GET) or form/JSON body (POST). Dataclasses with appropriate annotations are populated from the request data.
:::

```python
def get(doc_id: str, doc, store: DocumentStore):
    # doc_id from path, doc from _context.py, store from app.provide()
    return Page("doc.html", "content", doc=doc)
```

## When to Use Filesystem vs Decorator Routes

| Use filesystem routing when… | Use `@app.route()` when… |
|------------------------------|---------------------------|
| Routes map to a content hierarchy | Routes are API-like or action-oriented |
| Layouts and context cascade naturally | Each route is independent |
| You want co-located handlers and templates | You prefer explicit route registration |

You can mix both: `app.mount_pages("pages")` for the main app shell, and `@app.route("/api/...")` for API endpoints.

## Related

- [[docs/routing/routes|Routes]] — Decorator-based route registration
- [[docs/core-concepts/return-values|Return Values]] — `Page` and `LayoutPage`
- [[docs/templates/fragments|Fragments]] — Block-level rendering for htmx
- [[docs/tutorials/view-transitions-oob|View Transitions]] — Boosted navigation with layouts
