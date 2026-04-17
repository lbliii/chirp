---
title: OOB Registry & Fail-Loud Rendering
description: Register out-of-band shell regions, mark them optional, and understand BlockNotFoundError
draft: false
weight: 36
lang: en
type: doc
tags: [oob, shell, app-shell, htmx, contracts]
keywords: [oob, register_oob_region, BlockNotFoundError, optional, shell regions, fail-loud]
category: guide
---

## Why the Registry Exists

Chirp's render plan emits **out-of-band (OOB) fragments** to update shell regions —
breadcrumbs, sidebar, document title, topbar actions — on boosted navigation. The
**OOB registry** is the app-level source of truth that maps each block name (e.g.
`breadcrumbs_oob`) to:

- the **target DOM id** to swap into,
- the **swap strategy** (`innerHTML` vs `outerHTML`/`true`),
- whether to **wrap** the rendered HTML in a `<div id=... hx-swap-oob=...>`,
- whether the region is **optional** (may legitimately be absent from some layouts).

The registry lives beside routes, middleware, and fragment targets in the frozen
app state. It is consulted at two points:

1. **Startup** — the `oob_registry` contract check verifies every registered block
   is defined in at least one layout template.
2. **Render time** — `execute_render_plan` pre-checks block existence before
   calling `adapter.render_block`.

## Registering a Region

Use `app.register_oob_region()` during setup, before `app.run()`:

```python
app.register_oob_region(
    "breadcrumbs_oob",
    target_id="chirpui-topbar-breadcrumbs",
    swap="innerHTML",
    wrap=True,
)
```

| Kwarg | Default | Purpose |
|---|---|---|
| `target_id` | *required* | DOM id the OOB fragment replaces/updates |
| `swap` | `"innerHTML"` | htmx swap strategy (`"innerHTML"` or `"true"`) |
| `wrap` | `True` | Wrap output in `<div id=target_id hx-swap-oob=swap>`. Set `False` for tags like `<title>` that embed their own `hx-swap-oob` attribute |
| `optional` | `False` | See below — opt out of fail-loud behavior |

`use_chirp_ui()` auto-registers `breadcrumbs_oob`, `sidebar_oob`, `title_oob`, and
`shell_actions_oob` with `optional=True`. Your app only needs to register
project-specific regions.

## The Fail-Loud Policy (0.5+)

Before 0.5, a region update referencing a block that did not exist in the layout
was silently swallowed — the region was emitted with `html=""`, which wipes the
target element's DOM content on every boosted navigation. Scoped bugs like "my
breadcrumbs keep disappearing" were impossible to find from the server side.

As of 0.5, `execute_render_plan` pre-checks each region update against the
target template's `block_metadata()`:

- **Block exists** → render normally.
- **Block missing, region NOT optional** → raise `chirp.errors.BlockNotFoundError`.
- **Block missing, region IS optional** → drop the region from the response (no
  empty OOB wrapper is emitted; the existing DOM content stays put).

`BlockNotFoundError` multi-inherits from `ChirpError` and `KeyError`, so existing
`except KeyError` handlers (including Kida's `render_block` contract) still catch
it. The exception carries `.template`, `.block`, and `.region` for diagnostics.

### When to use `optional=True`

Mark a region optional when **it is expected to be absent from some layouts**.
The canonical example is chirp-ui's shell regions — an app using the full
`app_shell_layout.html` defines `breadcrumbs_oob` and `sidebar_oob`, but a bare
custom layout may not, and that's fine.

```python
app.register_oob_region(
    "breadcrumbs_oob",
    target_id="chirpui-topbar-breadcrumbs",
    swap="innerHTML",
    wrap=True,
    optional=True,   # shell region; apps without chirp-ui shell don't need it
)
```

Do **not** use `optional=True` to silence a typo or a forgotten `{% region %}`
declaration. The startup check distinguishes the two — non-optional orphans
emit ERROR, optional orphans emit WARNING — so fixing the former is mandatory
while the latter is advisory.

## Startup Contract Check

`app.check()` runs `check_oob_registry_coverage` automatically. For each block
in the registry, it walks all layout templates and verifies at least one
defines a matching block:

| Registered as | Layout defines? | Severity | Meaning |
|---|---|---|---|
| `optional=False` | yes | — | OK |
| `optional=False` | no | **ERROR** | Render would raise `BlockNotFoundError` |
| `optional=True` | yes | — | OK |
| `optional=True` | no | WARNING | Render silently skips; registration may be stale |

Run the check from tests:

```python
def test_app_contracts():
    app = make_app()
    issues = app.check()
    assert not [i for i in issues if i.severity is Severity.ERROR]
```

Apps that need the pre-0.5 permissive behavior can demote globally:

```python
app.override_contract_severity("oob_registry", Severity.WARNING)
```

This is an escape hatch for migration, not a supported long-term configuration.

## Defining the Block in the Layout

The registry only tracks metadata — you still need to define the block in a
layout template. The modern pattern uses `{% region %}`, which produces both a
regular block (for full-page renders) and an OOB-wrapped version (for fragment
swaps) from a single definition:

```html
{% region breadcrumbs_oob(breadcrumb_items=[]) %}
  {% if breadcrumb_items %}
    <nav aria-label="breadcrumb">...</nav>
  {% end %}
{% end %}
```

See [App Shells → Regions](./app-shell.md#regions-recommended-for-oob) for the
full pattern. Plain `{% block breadcrumbs_oob %}...{% endblock %}` also works
for cases where you don't need the dual full-page / OOB output.

## Troubleshooting `BlockNotFoundError`

```
BlockNotFoundError: Block 'breadcrumbs_oob' not found in template
'layouts/site.html' (OOB region 'chirpui-topbar-breadcrumbs'). Either add
the block to the layout template, or if this region is legitimately
optional, register it with optional=True.
```

The error points at the three real fixes:

1. **Add the block to the layout.** The registry says you promised this region
   exists; add `{% region breadcrumbs_oob %}...{% end %}` (or a plain
   `{% block %}`) to the layout template. This is the right fix 90% of the
   time — usually a missing layout region or a typo in the block name.

2. **Mark the region optional.** If the region is genuinely absent from some
   layouts by design, pass `optional=True` to `register_oob_region`. The render
   path will silently skip the region instead of raising. Use this when the
   region is a shell concern defined in a framework-level layout (like
   chirp-ui's app shell) and some routes use a custom layout without it.

3. **Remove the registration.** If the region is no longer used anywhere, drop
   the `register_oob_region` call. The WARNING from the startup check for
   optional orphans is precisely the signal that the registration is stale.

## Related

- [App Shells](./app-shell.md) — the regions pattern and shell actions
- [UI Layers & Shell Regions](./ui-layers.md) — vocabulary and swap scopes
- [RenderPlan Middleware](./render-plan.md) — inspecting the plan from middleware
