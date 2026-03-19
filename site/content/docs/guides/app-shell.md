---
title: App Shells
description: Persistent layout with SPA-style navigation and fragment regions
draft: false
weight: 35
lang: en
type: doc
tags: [app-shell, htmx, navigation, layout]
keywords: [app-shell, sidebar, navigation, fragment, page, boost, htmx]
category: guide
---

## What Is an App Shell?

An app shell is a persistent layout — topbar, sidebar, footer — that stays on
screen while the main content area swaps between pages.  Think Gmail, GitHub, or
any dashboard.  The shell never reloads; only `#main` changes.

Chirp + chirp-ui give you this pattern with zero client-side JavaScript
frameworks.  The server renders exactly the right HTML for each request, and
htmx swaps it in.

## How It Works

```
Full page load     → server renders everything (shell + page)
Sidebar navigation → server renders the page block, htmx swaps #main
Fragment request   → server renders just the targeted block
```

### The Navigation Model

Sidebar links carry explicit htmx attributes via `sidebar_link(boost=true)`:

```html
<a href="/contacts"
   hx-boost="true"
   hx-target="#main"
   hx-swap="innerHTML transition:true">Contacts</a>
```

`hx-boost` on the link itself sends the `HX-Boosted` header, which tells
Chirp to render the `page_block` (the wider, self-contained root).  The
response is swapped directly into `#main`.

**Nothing inside `<main>` inherits htmx attributes.**  Forms, buttons, and
interactive regions work without defensive wrappers.

### The Rendering Rule

Handlers return `Page` and Chirp auto-detects rendering scope:

```python
def get(request: Request) -> Page:
    return Page(
        "contacts/page.html",
        "page_content",
        page_block_name="page_root",
        **context,
    )
```

| Request type | What renders | Block used |
|---|---|---|
| Full page load | Shell + layouts + page | `page_root` (full template) |
| Sidebar navigation (`HX-Boosted`) | Page block only | `page_root` |
| Fragment request (form, search) | Narrow block only | `page_content` |

The developer doesn't think about `is_fragment` or `is_boosted`.  Return
`Page` with both block names and Chirp does the right thing.

## Building a Shell

### 1. Extend `app_shell_layout.html`

```html
{% extends "chirpui/app_shell_layout.html" %}
{% from "chirpui/sidebar.html" import sidebar, sidebar_link, sidebar_section %}

{% block brand %}My App{% end %}

{% block sidebar %}
{% call sidebar() %}
  {% call sidebar_section("Main") %}
    {{ sidebar_link("/", "Home", icon="home") }}
    {{ sidebar_link("/contacts", "Contacts", icon="grid") }}
  {% end %}
{% end %}
{% end %}

{% block content %}
  Page content here
{% end %}
```

`app_shell_layout.html` provides the topbar, sidebar slot, and `<main id="main">`.
Sidebar links get SPA navigation by default (`boost=true`).

### 2. Structure Your Page Template

```html
{% block page_root %}
<div class="my-page">
  <h1>Contacts</h1>

  {% block page_content %}
  <div id="contacts-list">
    {% for c in contacts %}
      <div>{{ c.name }}</div>
    {% end %}
  </div>
  {% endblock %}
</div>
{% endblock %}
```

- `page_root` — the wide block for sidebar navigation.  Contains layout
  wrappers, headings, spacing.
- `page_content` — the narrow block for fragment requests.  Contains just the
  data-driven content.

### 3. Return Page from Your Handler

```python
def get(request: Request) -> Page:
    contacts = get_contacts()
    return Page(
        "contacts/page.html",
        "page_content",
        page_block_name="page_root",
        contacts=contacts,
    )
```

### Regions (recommended for OOB)

When you need both full-page slots and OOB swaps (breadcrumbs, sidebar, title),
use `{% region %}` instead of blocks. One definition serves both — no duplication:

```html
{% region breadcrumbs_oob(breadcrumb_items=[{"label":"Home","href":"/"}]) %}
{{ breadcrumbs(breadcrumb_items) }}
{% end %}

{% region sidebar_oob(current_path="/") %}
{{ sidebar(current_path=current_path) }}
{% end %}

{% call app_shell(brand="My App") %}
  {% slot topbar %}
  {{ breadcrumbs_oob(breadcrumb_items=breadcrumb_items | default([{"label":"Home","href":"/"}])) }}
  {% end %}
  {% slot sidebar %}
  {{ sidebar_oob(current_path=current_path | default("/")) }}
  {% end %}
  {% block content %}{% end %}
{% end %}
```

See `examples/chirpui/shell_oob` for the reference implementation. The block-based
extend pattern above remains valid for apps that don't need OOB.

## Route Contract and Sections

With the [route directory contract](/docs/reference/route-contract/), sections, `_meta.py`, and shell context assembly replace manual `build_page_context` patterns. Register sections with `app.register_section()` before `mount_pages()`. Use `_meta.py` to declare `title`, `section`, `breadcrumb_label`, and `shell_mode`. The framework assembles `page_title`, `breadcrumb_items`, `tab_items`, and `current_path` automatically. See the [Route Directory Golden Path](/docs/guides/route-directory/) for recommended patterns.

## Forms Inside the Shell

Forms inside `<main>` work without any special wrappers.  Since `<main>` has no
inherited htmx attributes, form submissions target exactly what you specify:

```html
<form hx-post="/contacts/create"
      hx-target="#contacts-list"
      hx-swap="outerHTML">
  <input name="name" required>
  <button type="submit">Add</button>
</form>
```

No `fragment_island`, no `hx-disinherit`, no `beforeSwap` handler needed.

### Validation Errors

Return `ValidationError` to re-render a form block with 422 status:

```python
async def post(request: Request):
    form = await request.form()
    result = validate(form, rules)
    if not result:
        return ValidationError(
            "contacts/page.html",
            "contact_form",
            retarget="#contact-form-card",
            errors=result.errors,
            form=form,
        )
    # ... success path
```

## Shell Actions

Routes contribute actions to the topbar (buttons, links, menus) via
`_context.py` files. The correct pattern is to return a `context()` dict with
a `shell_actions` key — not a standalone `shell_actions()` function.

### Declaration

```python
# pages/contacts/_context.py
from chirp import ShellAction, ShellActions, ShellActionZone

def context() -> dict:
    return {
        "shell_actions": ShellActions(
            primary=ShellActionZone(
                items=(ShellAction(id="add", label="Add Contact", icon="add", href="/contacts/new"),),
            ),
        ),
    }
```

### Three Zones

- **primary** — Main buttons/links (e.g. "New project", "Deploy")
- **controls** — Secondary actions (e.g. "Metrics", filters)
- **overflow** — Dropdown menu (e.g. "More" with Archive, Export, Docs)

```python
ShellActions(
    primary=ShellActionZone(items=(ShellAction(id="new", label="New", href="/new"),)),
    controls=ShellActionZone(items=(ShellAction(id="metrics", label="Metrics", href="#stats"),)),
    overflow=ShellActionZone(
        items=(
            ShellAction(id="archive", label="Archive", href="/archive"),
            ShellAction(id="export", label="Export", href="/export"),
        ),
    ),
)
```

### Cascade Inheritance

Parent `_context.py` defines section defaults; child routes inherit them.
Child `_context.py` can add actions, override by `id`, or replace entire zones.

### Override Patterns

**Remove specific parent actions:**

```python
ShellActionZone(items=(...), remove=("parent-action-id",))
```

**Replace an entire zone** (e.g. form pages that need different actions):

```python
ShellActions(
    primary=ShellActionZone(
        items=(ShellAction(id="save", label="Save", href="/save"),),
        mode="replace",
    ),
)
```

Use `mode="replace"` when a subroute (e.g. settings, wizard, install) should
completely replace parent navigation actions. Cannot combine with `remove=`.

### Layout Wiring

When using `chirpui/app_shell_layout.html`, `shell_actions` is passed via the
layout chain from merged `_context.py` results. No extra wiring needed.

When using the `app_shell()` macro (regions-based layouts), pass it explicitly:

```html
{% call app_shell(brand="My App", shell_actions=shell_actions | default(none)) %}
  ...
{% end %}
```

### OOB Mechanism

Chirp's render plan adds shell actions as an OOB fragment when serving boosted
navigation requests or when the HTMX target has `triggers_shell_update=True`
(e.g. tab clicks targeting `#page-root`). The topbar updates automatically on
each page change — no client-side logic required.

`use_chirp_ui()` registers `main` and `page-root` with `triggers_shell_update=True`,
and `page-content-inner` with `triggers_shell_update=False` so narrow swaps
don't update the shell. Custom targets: `app.register_fragment_target("id",
fragment_block="...", triggers_shell_update=True)`.

### Reference

See `examples/chirpui/pages_shell` for a working cascade with `remove=` and
`mode="replace"`.

## Debugging and Introspection

The most useful way to debug a shell app is to follow the contract chain:

1. Which HTMX target fired? (`#main`, `#page-root`, or a narrow target)
2. Which fragment block does Chirp map that target to?
3. Does the leaf page template actually define that block?

With `use_chirp_ui(app)`, the default mapping is:

| Target | Block | Typical trigger |
|---|---|---|
| `#main` | `page_root` | Sidebar navigation |
| `#page-root` | `page_root_inner` | Section tabs |
| `#page-content-inner` | `page_content` | Narrow content mutations |

If the wrong amount of HTML swaps, the target/block pair is usually the bug. If the right block is chosen but the shell does not update, check whether the target was registered with `triggers_shell_update=True`.

For day-to-day debugging:

- Run `app.check()` in tests or startup to catch missing shell blocks early.
- When `config.debug=True`, response headers include `X-Chirp-Route-Kind`, `X-Chirp-Route-Meta`, `X-Chirp-Context-Chain`, and `X-Chirp-Shell-Context` for route introspection.
- Visit `/__chirp/routes` (debug only) for a visual route explorer with per-route drill-down.
- The HTMX debug panel's activity log shows route metadata when you expand a request entry.
- Prefer `render_route_tabs(tab_items, current_path)` over the legacy `route_tabs(...)` alias so template names do not collide with context variables.
- Keep one Python source of truth for tab families, breadcrumb prefixes, and sidebar state instead of recomputing them across templates and handlers.
- When a target is unregistered, Chirp's render-plan diagnostics list the known targets; use that output to spot typos quickly.

## Content Navigation Links

Sidebar links get SPA transitions automatically.  For links inside page
content that should also use SPA navigation (pagination, breadcrumbs,
interlinked pages), use the `nav_link` macro:

```html
{% from "chirpui/nav_link.html" import nav_link %}

{{ nav_link("/page-2", "Next page") }}

{% call nav_link("/details") %}View details{% end %}
```

Plain `<a>` tags work fine and do full-page loads.  Use `nav_link` only
when you want the smooth SPA transition within the shell.

## Fragment Regions (Optional)

The `fragment_island` / `safe_region` macros are ChirpUI/HTMX swap-safety
primitives. They isolate local mutation regions from inherited `hx-*` behavior
using `hx-disinherit`. Use them when you want semantic grouping or when a
region needs its own `hx-target` / `hx-swap` defaults:

```html
{% from "chirpui/fragment_island.html" import fragment_island %}

{% call fragment_island("contacts-page", hx_target="#contacts-page", hx_swap="outerHTML") %}
  {# forms inside here target #contacts-page by default #}
{% end %}
```

**Important:** `fragment_island` is not the same as Chirp's `data-island` islands.
`fragment_island` is a swap-safety boundary (no client runtime). Chirp islands
(`data-island`) are client-managed surfaces with mount/unmount lifecycle. See
[Islands Contract](islands.md) for the distinction.

## Custom Shells

If you need a custom shell instead of `app_shell_layout.html`, follow these
rules:

1. **No `hx-boost` on `<main>`** — put it on individual nav links instead
2. **Use `sidebar_link(boost=true)`** or add `hx-boost="true" hx-target="#main"
   hx-swap="innerHTML transition:true"` on each nav link
3. **No wrapper div inside `<main>`** — content renders directly; the server's
   `page_block` response is the raw content for `#main`

See `examples/chirpui/kanban_shell` for a working custom shell and `examples/chirpui/shell_oob` for
regions-based OOB.

## Gotchas for Interactive Shells

Interactive shells — boards, dashboards, real-time feeds — combine OOB swaps,
SSE, and action-style routes. These patterns have sharp edges worth knowing.

### OOB with `hx-swap="none"` — the Lost Main

Chirp's `OOB(main, *oob_fragments)` renders the first argument as the **main**
response (no `hx-swap-oob` wrapping). The rest get wrapped. When a button uses
`hx-swap="none"` (delete, move, toggle), the main is **discarded** — htmx only
processes the OOB elements.

If you put important content as the main, it vanishes silently:

```python
# BAD — old_column is the main, discarded by hx-swap="none"
return OOB(
    _column_fragment(old_status, tasks),
    _column_fragment(new_status, tasks),
    _stats_fragment(tasks),
)

# GOOD — empty main, all real content is OOB
return OOB(
    Fragment("page.html", "empty"),
    _column_fragment(old_status, tasks),
    _column_fragment(new_status, tasks),
    _stats_fragment(tasks),
)
```

**Rule of thumb:** if the route uses `hx-swap="none"`, make the OOB main an
empty fragment and put everything else in the OOB positions.

### SSE Event Naming — the Silent Mismatch

When you yield a `Fragment` with a `target` in an SSE generator,
`_format_event` uses the target as the SSE event name (e.g.,
`"column-backlog"`). But `sse-swap="fragment"` only listens for events
literally named `"fragment"`. Everything else is silently ignored.

**Fix:** Create template blocks with `hx-swap-oob` baked into the HTML, and
yield `Fragment` objects without `target`. The event name defaults to
`"fragment"` and htmx processes the OOB attributes from the content:

```html
{%- fragment column_block_oob -%}
{% call column(column_id, column_name, tasks | length, oob=true) %}
  ...
{% end %}
{%- endfragment -%}
```

```python
# No target → event name is "fragment" → client receives it
yield Fragment("page.html", "column_block_oob",
               column_id="backlog", tasks=filtered, ...)
```

### ContextVar Loss in SSE Generators

The SSE async generator runs in its own task, outside the middleware context.
Calling `get_user()`, `csrf_token()`, or any ContextVar-backed function inside
the generator raises `LookupError`.

**Fix:** Capture request-scoped values **before** entering the generator:

```python
def events_route():
    user = get_user()  # captured in handler scope

    async def generate():
        # user is available via closure; get_user() would fail here
        yield _fragment(..., current_user=user)

    return EventStream(generate())
```

### Dual Template Blocks for HTTP vs SSE

HTTP OOB routes rely on Chirp's negotiation layer to wrap fragments with
`hx-swap-oob`. SSE fragments are rendered by `_format_event`, which only adds
OOB wrapping when `target` is set — but setting `target` breaks event naming
(see above).

The result: you need separate template blocks for the same content. One for
HTTP (no inline OOB, the framework adds it) and one for SSE (OOB baked into
the HTML):

```html
{%- fragment column_block -%}
{# HTTP — negotiate() adds hx-swap-oob externally #}
{% call column(col_id, col_name, count, oob=false) %}...{% end %}
{%- endfragment -%}

{%- fragment column_block_oob -%}
{# SSE — OOB is inline so _format_event doesn't need target #}
{% call column(col_id, col_name, count, oob=true) %}...{% end %}
{%- endfragment -%}
```

See `examples/chirpui/kanban_shell` for a working example of all four patterns.
