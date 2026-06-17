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

An **app shell** is a layout that stays on screen — topbar, sidebar, footer —
while the main content area swaps between pages. Think Gmail or GitHub: the
chrome never reloads, only the content inside `#main` changes. It works with
zero client-side JavaScript framework: the server renders the right HTML for
each request and htmx swaps it in.

Reach for an app shell when you want SPA-style navigation around persistent
chrome. This page is the how-to for chirp-ui's `app_shell_layout.html`. For the
three shell options and when to pick each, see
[[docs/build-apps/ui-extensions/shells|the three shells and when to pick each]].

## How it works

```
Full page load     → server renders everything (shell + page)
Sidebar navigation → server renders the page block, htmx swaps #main
Fragment request   → server renders just the targeted block
```

The shell layout puts the [[docs/build-apps/ui-extensions/boosted-navigation|boost and swap contract]]
(`hx-boost`, `hx-target="#main"`, `hx-swap="innerHTML"`, `hx-select="#page-content"`)
on `<main id="main">`. Plain `<a href="...">` links inside `#main` inherit those
attributes, so they get SPA navigation with no extra markup. Because `#main`
swaps `innerHTML` (not `outerHTML`), the element persists in the DOM across
swaps.

:::{note} See also
The htmx boost/select/disinherit contract and cross-shell redirects are owned by
[[docs/build-apps/ui-extensions/boosted-navigation|Boosted Navigation]]. The
glossary (app shell vs page chrome vs surface chrome) and the stable OOB element
ids live in [[docs/build-apps/ui-extensions/ui-layers|shell regions and OOB element ids]].
:::

## Build a shell

The happy path is three steps: extend the layout, give your page a `page_root`
and a `page_content` block, and return [[docs/about/core-concepts/return-values|`Page`]]
with both block names.

::::{steps}

:::{step} Extend `app_shell_layout.html`

```html
{% extends "chirpui/app_shell_layout.html" %}
{% from "chirpui/sidebar.html" import sidebar, sidebar_link, sidebar_section %}

{% block brand %}My App{% end %}

{% block sidebar %}
{% call sidebar() %}
  {% call sidebar_section("Main") %}
    {{ sidebar_link("/", "Home", icon="house") }}
    {{ sidebar_link("/contacts", "Contacts", icon="users") }}
  {% end %}
{% end %}
{% end %}

{% block content %}
  Page content here
{% end %}
```

`app_shell_layout.html` provides the topbar, sidebar slot, and `<main id="main">`
with the boost/target/swap/select contract already wired. Links inside `#main`
inherit SPA navigation automatically.
:::{/step}

:::{step} Give your page a `page_root` and a `page_content` block

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

- `page_root` — the wide block for sidebar navigation. Contains layout wrappers,
  headings, spacing.
- `page_content` — the narrow block for fragment requests. Contains just the
  data-driven content.
:::{/step}

:::{step} Return `Page` with both block names

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
:::{/step}

::::{/steps}

## The rendering rule

Return `Page` with both block names and Chirp picks the right scope for each
request — the return type *is* the intent. You never branch on `is_htmx` or
`is_boosted` yourself.

:::{list-table}
:header-rows: 1

- - Request type
  - What renders
  - Block used
- - Full page load
  - Shell + layouts + page
  - `page_root` (full template)
- - Sidebar navigation (`HX-Boosted`)
  - Page block only
  - `page_root`
- - Fragment request (form, search)
  - Narrow block only
  - `page_content`
:::

:::{note}
If you ever need to inspect the request kind directly, use `request.is_htmx`
(any htmx request) or `request.is_narrow_fragment` (a narrow swap, excluding
boosted navigation and history restore). The older `request.is_fragment` is
deprecated — it is ambiguous for boosted navigations and emits a warning.
:::

### Active state

ChirpUI sidebar and navbar links take a `match=` parameter for automatic
path-based highlighting:

```html
{{ sidebar_link("/", "Home", icon="house", match="exact") }}
{{ sidebar_link("/contacts", "Contacts", icon="users", match="prefix") }}
```

`match="exact"` activates on an exact URL match; `match="prefix"` activates when
the URL starts with the href.

:::{tip}
Chirp auto-injects `current_path` into the template context for `Template(...)`
and `Page(...)` returns, so `match=` works without manually passing `nav=` or
`current_path=` from every handler.
:::

## OOB regions

When you need both full-page slots and out-of-band swaps (breadcrumbs, sidebar,
title), use `{% region %}` instead of plain blocks. One definition serves both —
no duplication:

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

## Forms inside the shell

Forms with an explicit `hx-target` override the inherited shell attributes
naturally — no defensive wrappers needed:

```html
<form hx-post="/contacts/create"
      hx-target="#contacts-list"
      hx-swap="outerHTML">
  <input name="name" required>
  <button type="submit">Add</button>
</form>
```

Use `fragment_island` or `hx-disinherit` only when a region needs to fully opt
out of the inherited boost/target/swap/select chain.

To re-render a form block on a validation failure, return
[[docs/build-apps/forms-data/forms-validation|`ValidationError`]] with the form
block name and a 422 status:

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

## Shell actions

Routes contribute actions to the topbar (buttons, links, menus) by returning a
`context()` dict with a `shell_actions` key from a `_context.py` file — not a
standalone `shell_actions()` function.

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

There are three zones:

- **primary** — main buttons/links (e.g. "New project", "Deploy").
- **controls** — secondary actions (e.g. "Metrics", filters).
- **overflow** — dropdown menu (e.g. "More" with Archive, Export, Docs).

When you extend `chirpui/app_shell_layout.html`, `shell_actions` is passed
through the layout chain from the merged `_context.py` results — no extra wiring.
When you use the `app_shell()` macro (regions-based layouts), pass it explicitly:

```html
{% call app_shell(brand="My App", shell_actions=shell_actions | default(none)) %}
  ...
{% end %}
```

:::{note}
`ShellAction`, `ShellActions`, and `ShellActionZone` are **provisional** — the
shape of these APIs may change in a future release. The cascade and form-action
behavior below is stable in practice; see `examples/chirpui/pages_shell` for a
working reference.
:::

:::{dropdown} Advanced: form actions (`kind="form"`)
Use `kind="form"` for POST actions that need CSRF, hidden fields, and optional
htmx attributes on the rendered `<form>`. Chirp-ui renders the form in the shell
target; OOB updates refresh it on navigation like other shell actions.

- Put form actions in **primary** or **controls** only (not **overflow**).
- Set `form_action`, `label` (the submit button text), and optional
  `hidden_fields` as `tuple[tuple[str, str], ...]`.
- `include_csrf` (default `True`) renders `{{ csrf_field() }}` inside the form.
- htmx: set `hx_post`, `hx_target`, `hx_swap`, `hx_disinherit` as needed.
- `submit_surface`: `"btn"` | `"shimmer"` | `"pulsing"` (the ChirpUI submit
  control).

For link/button actions that need extra attributes (e.g. `hx-boost` on a shell
link), set `attrs` on `ShellAction` (a string passed through to the `btn`
macro).

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
:::

:::{dropdown} Advanced: cascade and override patterns
A parent `_context.py` defines section defaults; child routes inherit them. A
child `_context.py` can add actions, override an action by `id`, or replace an
entire zone.

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

Use `mode="replace"` when a subroute (settings, wizard, install) should
completely replace the parent's navigation actions. It cannot be combined with
`remove=`.
:::

:::{dropdown} Advanced: how shell actions reach the topbar (OOB)
Chirp's render plan adds shell actions as an OOB fragment when serving a boosted
navigation request, or when the htmx target was registered with
`triggers_shell_update=True` (e.g. tab clicks targeting `#page-root`). The
topbar updates on each page change with no client-side logic.

`use_chirp_ui()` registers `main` and `page-root` with
`triggers_shell_update=True`, and `page-content-inner` with
`triggers_shell_update=False` so narrow swaps don't update the shell. Register
your own targets with:

```python
app.register_fragment_target(
    "my-target",
    fragment_block="my_block",
    triggers_shell_update=True,
)
```
:::

## Route contract and sections

With the [[docs/quality/contracts-debugging/route-contract|route directory contract]],
sections, `_meta.py`, and shell-context assembly replace manual
`build_page_context` patterns. Register sections with `app.register_section()`
before `mount_pages()`, and use `_meta.py` to declare `title`, `section`,
`breadcrumb_label`, and `shell_mode`. The framework assembles `page_title`,
`breadcrumb_items`, `tab_items`, and `current_path` automatically. See the
[[docs/build-apps/pages-navigation/route-directory|Route Directory Golden Path]]
for the recommended patterns.

## Debugging a shell

The most useful way to debug a shell app is to follow the contract chain:

1. Which htmx target fired? (`#main`, `#page-root`, or a narrow target.)
2. Which fragment block does Chirp map that target to?
3. Does the leaf page template actually define that block?

With `use_chirp_ui(app)`, the default target → block mapping is:

:::{list-table}
:header-rows: 1

- - Target
  - Block
  - Typical trigger
- - `#main`
  - `page_root`
  - Sidebar navigation
- - `#page-root`
  - `page_root_inner`
  - Section tabs
- - `#page-content-inner`
  - `page_content`
  - Narrow content mutations
:::

If the wrong amount of HTML swaps, the target/block pair is usually the bug. If
the right block is chosen but the shell doesn't update, check whether the target
was registered with `triggers_shell_update=True`.

For day-to-day debugging:

- Run `app.check()` in tests or at startup to catch missing shell blocks early.
- When `config.debug=True`, response headers include `X-Chirp-Route-Kind`,
  `X-Chirp-Route-Meta`, `X-Chirp-Context-Chain`, and `X-Chirp-Shell-Context` for
  route introspection.
- Visit `/__chirp/routes` (debug only) for a visual route explorer with per-route
  drill-down.
- Prefer `render_route_tabs(tab_items, current_path)` over the legacy
  `route_tabs(...)` alias so template names don't collide with context variables.
- Keep one Python source of truth for tab families, breadcrumb prefixes, and
  sidebar state instead of recomputing them across templates and handlers.

## Content links and fragment regions

Since `<main id="main">` carries the boost contract, all `<a>` tags inside page
content get SPA navigation automatically — no special attributes needed:

```html
<a href="/page-2">Next page</a>
<a href="/details">View details</a>
```

For a smooth SPA transition effect on a specific content link, use the
`nav_link` macro (it puts `hx-boost` on the link itself):

```html
{% from "chirpui/nav_link.html" import nav_link %}
{{ nav_link("/page-2", "Next page") }}
```

To opt a link out of SPA navigation, add `hx-boost="false"`.

The `fragment_island` / `safe_region` macros isolate a local mutation region
from inherited `hx-*` behavior using `hx-disinherit`. Use them when a region
needs its own `hx-target` / `hx-swap` defaults:

```html
{% from "chirpui/fragment_island.html" import fragment_island %}

{% call fragment_island("contacts-page", hx_target="#contacts-page", hx_swap="outerHTML") %}
  {# forms inside here target #contacts-page by default #}
{% end %}
```

:::{warning}
`fragment_island` is **not** the same as Chirp's `data-island` islands.
`fragment_island` is a swap-safety boundary with no client runtime; `data-island`
marks a client-managed surface with a mount/unmount lifecycle. See the
[[docs/build-apps/ui-extensions/islands|Islands Contract]] for the distinction.
:::

:::{dropdown} Building a shell without chirp-ui
If you need a custom shell instead of `app_shell_layout.html`, replicate the
boost contract on your own `<main>` element:

```html
<main id="main" class="my-shell__main" tabindex="-1"
      hx-boost="true" hx-target="#main" hx-swap="innerHTML" hx-select="#page-content">
  <div id="page-content">
    {% block content %}{% end %}
  </div>
</main>
```

Sidebar links live *outside* `#main`, so they don't inherit from it — give them
their own `hx-target="#main"` and `hx-select="#page-content"`. See
`examples/chirpui/kanban_shell` for a working custom shell and
`examples/chirpui/shell_oob` for the regions-based OOB variant.
:::

## Interactive shells

Boards, dashboards, and real-time feeds combine OOB swaps, SSE, and action-style
routes. Those patterns have sharp edges around how the *main* response and SSE
event names interact with htmx — but they are streaming concerns, not app-shell
concerns, and they apply to any layout.

:::{note} See also
- [[docs/build-apps/streaming-updates/sse-patterns|SSE patterns]] — the
  `OOB(main, *oob_fragments)` "lost main" footgun (an `hx-swap="none"` button
  discards the main response) and SSE event-name matching.
- [[docs/build-apps/streaming-updates/server-sent-events|Server-Sent Events]] —
  how `EventStream` yields fragments and how the SSE event name is chosen.
- [[docs/build-apps/streaming-updates/html-streaming|Streaming HTML]] —
  capturing `ContextVar`-backed request state (auth, CSRF, session) *before*
  returning a stream, since middleware-scoped helpers can raise `LookupError`
  during deferred or streamed rendering.
:::

:::{note} Next steps
- [[docs/build-apps/ui-extensions/shells|Shells]] — pick the right shell for your app.
- [[docs/build-apps/ui-extensions/ui-layers|UI layers & shell regions]] — the layout vocabulary and stable OOB ids.
- [[docs/build-apps/ui-extensions/boosted-navigation|Boosted Navigation]] — the swap contract and debug warnings.
- [[docs/build-apps/ui-extensions/islands|Islands]] — client-managed surfaces vs swap-safety regions.
- [[docs/build-apps/pages-navigation/route-directory|Route Directory]] — sections, `_meta.py`, and shell-context assembly.
:::

:::{related}
:::
