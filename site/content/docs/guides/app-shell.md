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

`app_shell_layout.html` puts `hx-boost="true"`, `hx-target="#main"`,
`hx-swap="innerHTML"`, and `hx-select="#page-content"` directly on `<main id="main">`.
Content is wrapped in `<div id="page-content">` inside `#main`. All links inside
`#main` inherit these attributes automatically — plain `<a href="...">` tags get
SPA navigation with no extra markup. Because `#main` uses `innerHTML` (not
`outerHTML`), it persists in the DOM and its `view-transition-name` is never
duplicated during swaps.

Sidebar links (outside `#main`) carry their own htmx attributes via
`sidebar_link()`, which emits `hx-boost`, `hx-target`, and `hx-select`.

When a boosted link fires, the `HX-Boosted` header tells Chirp to render
the `page_block` (the wider, self-contained root). The response is swapped
into `#main`.

Forms and fragment targets with explicit `hx-target` (e.g.
`hx-target="#contacts-list"`) override the inherited value naturally.
Use `fragment_island` or `hx-disinherit` only when a region needs to
opt out of the inherited shell attributes entirely.

### Active State

ChirpUI sidebar and navbar links support a `match=` parameter for automatic
path-based highlighting:

```html
{{ sidebar_link("/", "Home", icon="◉", match="exact") }}
{{ sidebar_link("/contacts", "Contacts", icon="◎", match="prefix") }}
```

`match="exact"` activates on exact URL match; `match="prefix"` activates when the
URL starts with the href.  Chirp auto-injects `current_path` into template context
for `Template(...)` and `Page(...)` returns, so `match=` works without manually
passing `nav=` or `current_path=` from every handler.

After htmx navigation, `app_shell_layout.html` runs a client-side sync that
updates active classes and `aria-current="page"` based on `location.pathname`.
This covers the gap where `hx-boost` swaps `#main` but the sidebar DOM is
not re-rendered.

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

`app_shell_layout.html` provides the topbar, sidebar slot, and `<main id="main">`
with built-in `hx-boost`, `hx-target`, `hx-swap`, and `hx-select`. Links inside
`#main` inherit SPA navigation automatically.

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

Forms with explicit `hx-target` override the inherited shell attributes
naturally. No defensive wrappers needed:

```html
<form hx-post="/contacts/create"
      hx-target="#contacts-list"
      hx-swap="outerHTML">
  <input name="name" required>
  <button type="submit">Add</button>
</form>
```

Use `fragment_island` or `hx-disinherit` only when a region needs to fully
opt out of the inherited boost/target/swap/select chain.

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

### Form actions (`kind="form"`)

Use **`kind="form"`** for POST actions that need CSRF, hidden fields, and optional HTMX
attributes on the `<form>`. Chirp-ui renders the form in the shell target; OOB updates
refresh it on navigation like other shell actions.

- Put form actions in **primary** or **controls** only (not **overflow**).
- Set **`form_action`**, **`label`** (submit button), and optional **`hidden_fields`** as
  `tuple[tuple[str, str], ...]`.
- **`include_csrf`** (default `True`) renders `{{ csrf_field() }}` inside the form.
- HTMX: set **`hx_post`**, **`hx_target`**, **`hx_swap`**, **`hx_disinherit`** as needed.
- **`submit_surface`**: `"btn"` | `"shimmer"` | `"pulsing"` (ChirpUI submit control).

For link/button actions that need extra attributes (e.g. `hx-boost` on a shell link),
set **`attrs`** on `ShellAction` (string passed through to `btn`).

```python
ShellAction(
    id="add-to-party",
    kind="form",
    label="Add Bulbasaur to party",
    variant="primary",
    form_action="/team/add",
    hidden_fields=(("pokemon_id", "1"),),
    hx_post="/team/add",
    hx_target="#party-toast",
    hx_swap="innerHTML",
    hx_disinherit="hx-select",
    submit_surface="shimmer",
)
```

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

Since `<main id="main">` carries `hx-boost="true"`, all `<a>` tags inside
page content get SPA navigation automatically — no special attributes needed.

```html
<a href="/page-2">Next page</a>
<a href="/details">View details</a>
```

For links that need extra htmx attributes (e.g. `hx-push-url`), use the
`nav_link` macro:

```html
{% from "chirpui/nav_link.html" import nav_link %}
{{ nav_link("/page-2", "Next page", push_url=true) }}
```

To opt a link out of SPA navigation, add `hx-boost="false"`.

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

If you need a custom shell instead of `app_shell_layout.html`, replicate
the built-in defaults on your `<main>` element:

```html
<main id="main" class="my-shell__main" tabindex="-1"
      hx-boost="true" hx-target="#main" hx-swap="innerHTML" hx-select="#page-content">
  <div id="page-content">
    {% block content %}{% end %}
  </div>
</main>
```

Sidebar links (outside `#main`) need their own `hx-target="#main"` and
`hx-select="#page-content"` since they don't inherit from the `<main>` element.

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
