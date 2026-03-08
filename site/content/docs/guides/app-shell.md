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

Routes can contribute actions to the topbar (buttons, links, menus) via
`_context.py` files in the page directory:

```python
# pages/contacts/_context.py
from chirp.pages.shell_actions import ShellActions, ShellAction, ShellActionZone

def shell_actions() -> ShellActions:
    return ShellActions(
        primary=ShellActionZone(
            items=(
                ShellAction(id="add", label="Add Contact", icon="add", href="/contacts/new"),
            ),
        ),
    )
```

Shell actions are delivered via OOB swap when navigating between pages —
the topbar updates automatically.  Child routes inherit parent actions and
can override or remove them.

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

The `fragment_island` / `safe_region` macros still work but are no longer
required for correctness.  Use them when you want semantic grouping or
when a region needs its own `hx-target` / `hx-swap` defaults:

```html
{% from "chirpui/fragment_island.html" import fragment_island %}

{% call fragment_island("contacts-page", hx_target="#contacts-page", hx_swap="outerHTML") %}
  {# forms inside here target #contacts-page by default #}
{% end %}
```

## Custom Shells

If you need a custom shell instead of `app_shell_layout.html`, follow these
rules:

1. **No `hx-boost` on `<main>`** — put it on individual nav links instead
2. **Use `sidebar_link(boost=true)`** or add `hx-boost="true" hx-target="#main"
   hx-swap="innerHTML transition:true"` on each nav link
3. **Keep `<div id="page-content">` inside `<main>`** so the layout chain
   can find the content target

See `examples/kanban_shell` for a working custom shell.
