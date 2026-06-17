---
title: Route Directory Golden Path
description: The recommended file-by-file layout for an app-shell route in Chirp's filesystem routing
draft: false
weight: 30
lang: en
type: doc
tags: [routing, app-shell, golden-path, chirp-ui]
keywords: [route directory, _meta.py, sections, app-shell, golden path]
category: guide
---

When you build an app-shell application — a persistent topbar, sidebar, and tabs
around your pages — every route ends up needing the same handful of files. This
page is the recommended layout for one section member and one detail route: the
smallest set of files that gives you tabs, breadcrumbs, a data loader, and a
mutation handler with no boilerplate you don't need.

It assumes you already know Chirp's
[[docs/build-apps/pages-navigation/filesystem-routing|filesystem routing]] and
[[docs/build-apps/ui-extensions/app-shell|app shell]]; here we show only the
canonical file-by-file recipe.

:::{note}
This is the recommended convention, not the only valid layout. Filesystem
routing supports plenty of shapes; the golden path is the one that needs the
least wiring for a tabbed section.
:::

## When to use each file

A route directory holds `page.py` and `page.html` plus optional cascade files.
Reach for one of the special files only when you need what it provides:

:::{list-table}
:header-rows: 1

* - You need…
  - Use this file
* - Route metadata (title, section, breadcrumb)
  - `_meta.py`
* - Context shared down the tree (load an entity once)
  - `_context.py`
* - POST handlers for mutations
  - `_actions.py`
* - The handler and its template
  - `page.py` + `page.html`
* - A layout wrapper for this subtree
  - `_layout.html`
* - Heavier view assembly than a `_context.py` should hold
  - `_viewmodel.py`
:::

The cascade rules — how `_meta.py`, `_context.py`, and `_layout.html` flow down
to child routes — live in
[[docs/build-apps/pages-navigation/filesystem-routing|filesystem routing]]. This
page only shows which file does which job.

## Build an app-shell route

A section-member page needs three files. Build them in order.

::::{steps}

:::{step} Declare metadata in `_meta.py`
A static `RouteMeta` gives the shell its title, section, breadcrumb label, and
shell mode.

```python
from chirp.pages.types import RouteMeta

META = RouteMeta(
    title="Skills",
    section="discover",
    breadcrumb_label="Skills",
    shell_mode="tabbed",
)
```

`section` ties this page to a registered `Section` so the shell knows which tabs
to render.
:::{/step}

:::{step} Load domain data in `page.py`
The handler returns a [[docs/about/core-concepts/return-values|`Page`]] — a
fragment for htmx swaps, a full page for browser navigation. It carries only
your data; the shell, tabs, and breadcrumbs come from the section.

```python
from chirp import Page

def get():
    return Page("page.html", "content", items=load_items())
```
:::{/step}

:::{step} Render standard blocks in `page.html`
The page template fills the shell's content region. Put your markup inside the
`page_content` block.

```html
{% block page_root %}
{% block page_root_inner %}
{% block page_content %}
  {{ items }}
{% end %}
{% end %}
{% end %}
```
:::{/step}

::::{/steps}

:::{tip}
You do not need a `_context.py` here. When the section already supplies tabs and
breadcrumbs, the page only carries its own data.
:::

## Register the section

Sections live in `app.py`. Register each section, then mount your pages.

```python
from chirp.pages.types import Section, TabItem

app.register_section(Section(
    id="discover",
    label="Discover",
    tab_items=(
        TabItem(label="Skills", href="/skills"),
        TabItem(label="Chains", href="/chains"),
    ),
    breadcrumb_prefix=({"label": "App", "href": "/"},),
))
app.mount_pages("pages")
```

:::{note}
Register every section during setup, before you freeze the app. Section
resolution runs per request against the live registry, so registration order
relative to `mount_pages()` does not matter — registering sections first is just
a tidy convention. Once the app is frozen, `register_section()` raises.
:::

See [[docs/build-apps/ui-extensions/shells|shells]] for how sections, tabs, and
breadcrumbs render into the surrounding chrome.

## Add a detail route

A dynamic segment like `{name}/` follows the same three-file shape, with two
files that vary by parameter. The cascade injects the loaded entity into the
handler by name, so `page.py` stays a one-liner.

**`_meta.py`** — a `meta()` callable for a per-entity title:

```python
from chirp.pages.types import RouteMeta

def meta(name: str) -> RouteMeta:
    return RouteMeta(title=f"Skill: {name}", breadcrumb_label=name)
```

**`_context.py`** — load the entity once, or raise `NotFound`:

```python
from chirp import NotFound

def context(name: str) -> dict:
    skill = store.get(name)
    if not skill:
        raise NotFound()
    return {"skill": skill}
```

**`page.py`** — the handler receives `skill` from the cascade context by
parameter name:

```python
from chirp import Page

def get(skill):
    return Page("page.html", "content", skill=skill)
```

## Add a mutation route

Mutations live in `_actions.py`. Decorate each handler with `@action`; the
decorator name is the value templates send in the `_action` form field, which
dispatches to the matching handler.

```python
from chirp import Fragment
from chirp.pages.actions import action

@action("save")
def save(skill_id: str, name: str):
    update_skill(skill_id, name)
    return Fragment("page.html", "skill_row", skill=load_skill(skill_id))
```

The handler receives `skill_id` from the cascade context and `name` from the
form field named `name`. Each parameter is resolved by name against path params,
cascade context, then form fields — there is no automatic whole-form binding.

See [[docs/build-apps/forms-data/forms-validation|form validation and `_action`
dispatch]] for how the form field maps to the handler and how to validate input.

::::{dropdown} Advanced: fragment and shell updates
For partial swaps, return a [[docs/build-apps/html-fragments/fragments|`Fragment`]]
of a named block in `page.html`. To also update regions of the surrounding shell
in the same response — a counter in the topbar, a breadcrumb — emit out-of-band
swaps that target registered shell regions.

Out-of-band region updates fail loud: a swap that targets a block the layout
does not define raises rather than silently wiping the DOM. Register and
validate these targets through the OOB registry.

For shell-region updates specifically, Chirp exposes a `shell_actions` context
key. The exact mechanism is documented with the shell, not here.

:::{note} See also
- [[docs/quality/contracts-debugging/oob-registry|OOB regions]] — register and validate out-of-band swap targets
- [[docs/build-apps/ui-extensions/app-shell|app shell]] — shell regions and `shell_actions`
:::

::::{/dropdown}

:::{note} See also
- [[docs/build-apps/pages-navigation/filesystem-routing|Filesystem routing]] — the cascade and discovery rules behind these files
- [[docs/build-apps/ui-extensions/app-shell|App shell]] — the topbar, sidebar, and tabs this layout targets
- [[docs/build-apps/forms-data/forms-validation|Forms and validation]] — `_action` dispatch and input validation
:::
