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

You can also return `Suspense` for instant first paint with deferred blocks. The layout chain is applied automatically — the shell gets the full layout (head, CSS, sidebar), and OOB swaps target block IDs inside the page.

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

### How `render_with_blocks` works

Chirp composes layouts using `render_with_blocks({"content": page_html})`. This **replaces** `{% block content %}` with the pre-rendered page HTML. Any markup you put inside `{% block content %}` in your layout is overridden — it never renders.

This means persistent UI (navbars, sidebars, topbars) must live **outside** `{% block content %}`:

```html
{# target: main #}
{# ❌ Shell is INSIDE content — gets replaced, never renders #}
{% extends "chirpui/app_layout.html" %}
{% block content %}
  <nav>...</nav>
  {% block page_content %}{% end %}
{% end %}
```

```html
{# target: main #}
{# ✅ Shell is OUTSIDE content — always renders #}
<nav>...</nav>
<main id="main">
  <div id="page-content">
    {% block content %}{% end %}
  </div>
</main>
```

### Layout ramp: boost → shell → nested shells

Chirp offers three layout patterns, from simplest to most structured:

| Layout | Use case |
|--------|----------|
| `chirp/layouts/boost.html` | Simple pages, no persistent shell. Uses `hx-select="#page-content"` for fragment swaps. |
| `chirp/layouts/shell.html` | Persistent shell (topbar, sidebar). Override `{% block shell %}` to wrap main. |
| `chirpui/app_shell_layout.html` | ChirpUI apps — extends shell.html with sidebar, toast, CSS. |
| Nested shells | Forum > subforum > thread. Use `shell_section` macro for inner levels. |

**hx-select vs hx-disinherit**: Prefer `hx-select="#page-content"` on the boosted container. When the server returns a full HTML page, htmx extracts only `#page-content` for the swap. `hx-disinherit` breaks inheritance for fragment swaps; use `hx-target="this"` on event-driven elements instead (the `safe_target` middleware auto-injects this).

### Persistent app shell pattern

For dashboard-style apps with a topbar, sidebar, and content area, extend `chirpui/app_shell_layout.html` (if using ChirpUI) or `chirp/layouts/shell.html`:

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

Or without ChirpUI, extend `chirp/layouts/shell.html` and override `{% block shell %}`.

Key elements:

- **Extend shell.html or app_shell_layout.html** — Don't extend `boost.html` for app shell layouts.
- **`hx-boost="true"`** on `<main id="main">` — Boosted links inside the content area use AJAX navigation.
- **`hx-select="#page-content"`** — When the server returns a full HTML page, htmx parses it and extracts only `#page-content` for the swap. The shell persists client-side.
- **No `hx-disinherit`** on the content wrapper — Boosted links must inherit `hx-target`, `hx-swap`, and `hx-select` from `#main`. Fragment requests with explicit `hx-target` override the inherited value.
- **`{# target: main #}`** — Tells Chirp which layout depth to render for `HX-Target: main` requests.

### Nested shells with shell_section

For multi-level layouts (e.g. forum > subforum > thread), use the `shell_section` macro:

```html
{# target: items-content #}
{% from "chirp/macros/shell.html" import shell_section %}
<div class="chirpui-shell-section">
  <nav class="chirpui-shell-section__nav">Items</nav>
  {% call shell_section("items-content") %}
    {% block content %}{% end %}
  {% end %}
</div>
```

Inner layouts don't need `hx-select` — the renderer produces fragments for them. Use `chirp new myapp --shell` to scaffold a project with this pattern.

### Common mistakes

- **`{% extends %}` in inner layouts** — Inner `_layout.html` files that use `{% extends %}` can conflict with `render_with_blocks`. The child template may wipe the shell. Prefer composing with `shell_section` instead.
- **Missing `{# target: X #}` on inner layouts** — Non-root layouts default to `"body"` if no target is declared. Add `{# target: element_id #}` so the layout chain resolves correctly.
- **`hx-disinherit` in shell layouts** — Prefer `hx-select` on the parent. Use `hx-target="this"` on event-driven elements (e.g. SSE) instead of `hx-disinherit`.
- **Duplicate targets in a chain** — Two layouts with the same target cause `find_start_index_for_target` to return the first match. Use unique targets per layout.

## Context Cascade

`_context.py` files export a `context` function that provides shared data to handlers. Context cascades from root to leaf; child context overrides parent.

### Provider Signatures

Context providers receive arguments from two sources:

1. **Path parameters** — From the URL match (e.g. `doc_id` from `/documents/{doc_id}`)
2. **Parent context** — Values from providers higher in the filesystem tree

```python
# pages/_context.py — root provider, no params
def context() -> dict:
    return {"store": get_store(), "data_dir": "..."}

# pages/documents/{doc_id}/_context.py — child receives doc_id from path, store from parent
def context(doc_id: str, store) -> dict:
    doc = store.get(doc_id)
    if doc is None:
        raise NotFound(f"Document '{doc_id}' not found")
    return {"doc": doc}
```

For `/documents/abc-123`, the root provider runs first and adds `store` and `data_dir`. The child provider then receives `doc_id="abc-123"` from the path and `store` from the accumulated context.

**Service providers:** Context providers can also request types registered via `app.provide()`. Parameters with matching type annotations are resolved from the service provider factories:

```python
# pages/documents/{doc_id}/_context.py
def context(doc_id: str, store: DocumentStore) -> dict:
    doc = store.get(doc_id)
    return {"doc": doc}
```

With `app.provide(DocumentStore, get_store)`, the `store` param is injected from the factory.

### Early Abort with HTTPError

Providers may raise `NotFound` (or other `HTTPError` subclasses) to abort the cascade. Chirp renders the appropriate error page automatically.

```python
# pages/documents/{doc_id}/_context.py
from chirp import NotFound

def context(doc_id: str) -> dict:
    doc = store.get(doc_id)
    if doc is None:
        raise NotFound(f"Document {doc_id} not found")
    return {"doc": doc}
```

Handlers receive context as keyword arguments. Providers can be sync or async.

### Route-Scoped Shell Actions

`_context.py` can also return a reserved `shell_actions` value to drive persistent
shell chrome such as a global top bar. Shell actions cascade root-to-leaf just
like other context, but they merge by stable action `id` instead of plain dict
overwrite:

- child routes inherit parent actions by default
- child routes can override an inherited action by `id`
- child routes can remove inherited actions by `id`
- a zone can `replace` its inherited actions entirely

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

The resolved `shell_actions` object is available in page and layout templates.
For boosted shell navigations, Chirp also emits an out-of-band refresh for the
default target `#chirp-shell-actions`, so persistent top bars stay in sync as
the active route changes.

## Template Convention

When a route file has a sibling `.html` file with the same stem, that template is used implicitly:

- `page.py` + `page.html` → handler returns `Page("path/to/page.html", "content", ...)`
- `edit.py` + `edit.html` → handler returns `Page("path/to/edit.html", "content", ...)`

Template paths are relative to the pages root. The handler must pass the correct path to `Page()`.

For layout-heavy pages, prefer a self-contained page root plus narrower inner fragments:

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
    "page_content",
    page_block_name="page_root",
    items=load_items(),
)
```

This gives Chirp two safe render scopes:

- `page_content` for explicit fragment swaps into a narrow target
- `page_root` for boosted navigation, where the response must carry page-level wrappers such as stacks, toolbars, and spacing

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
