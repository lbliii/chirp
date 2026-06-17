---
title: OOB Registry & Fail-Loud Rendering
description: Register out-of-band shell regions, mark them optional, and fix BlockNotFoundError
draft: false
weight: 20
lang: en
type: doc
tags: [oob, shell, app-shell, htmx, contracts]
keywords: [oob, register_oob_region, BlockNotFoundError, optional, shell regions, fail-loud]
category: guide
---

## Overview

You added a shell region — breadcrumbs, a sidebar, a document title — and on boosted navigation it either raises `BlockNotFoundError` or silently vanishes from the page. This page shows you how to register an [[docs/build-apps/html-fragments/fragments|out-of-band (OOB)]] region, when to mark it `optional`, and how to read the error.

The **OOB registry** is your app's map from a template block name (like `breadcrumbs_oob`) to the DOM element it swaps into. Chirp checks that map at startup and again at render time, so a missing region fails loudly instead of wiping live DOM content.

:::{warning} The error you arrived with
```
BlockNotFoundError: Block 'breadcrumbs_oob' not found in template
'layouts/site.html' (OOB region 'chirpui-topbar-breadcrumbs').
```
You registered a region but no layout template defines a matching block. Chirp raises rather than emit an empty OOB swap that would erase whatever is already in that DOM element. The **Fix `BlockNotFoundError`** section below walks the three fixes in order.
:::

## Register a region

Call `app.register_oob_region()` during setup, before `app.run()`:

```python
app.register_oob_region(
    "breadcrumbs_oob",
    target_id="chirpui-topbar-breadcrumbs",
    swap="innerHTML",
)
```

The three kwargs you set in practice:

:::{list-table}
:header-rows: 1

* - Kwarg
  - Default
  - What it does
* - `target_id`
  - *required*
  - The DOM id the OOB fragment updates.
* - `swap`
  - `"innerHTML"`
  - The htmx swap strategy. `innerHTML` and `outerHTML` are the common ones; the validator accepts any htmx strategy plus modifiers.
* - `optional`
  - `False`
  - When `True`, layouts may legitimately omit this block. See [below](#when-to-mark-a-region-optional).
:::

:::{note}
With [[docs/build-apps/ui-extensions/chirp-ui|chirp-ui]] enabled, `use_chirp_ui()` already registers `breadcrumbs_oob`, `sidebar_oob`, and `title_oob` (all `optional=True`). Chirp's compiler also registers a `shell_actions_oob` fallback at freeze if you haven't. You only register your project's own regions.
:::

Defining the matching block in your layout is part of the [[docs/build-apps/ui-extensions/app-shell|app-shell `{% region %}` pattern]] — one definition serves both full-page renders and OOB swaps. Plain `{% block name %}...{% endblock %}` works too when you don't need the dual output.

## Fix `BlockNotFoundError`

The error names the block, the template, and the target DOM id. Work down these in order — the first one is the right fix the vast majority of the time.

::::{steps}
:::{step} Add the block to the layout
The registry says you promised this region exists. Add it to the layout template the error names:

```html
{% region breadcrumbs_oob(breadcrumb_items=[]) %}
  {% if breadcrumb_items %}
    <nav aria-label="breadcrumb">...</nav>
  {% end %}
{% end %}
```

This is the fix when the cause is a missing layout region or a typo in the block name.
:::{/step}
:::{step} Mark the region optional
If the region is genuinely absent from *some* layouts by design — a shell concern defined in a framework-level layout that custom routes skip — pass `optional=True`. The render path then drops the region instead of raising. See [when to mark a region optional](#when-to-mark-a-region-optional).
:::{/step}
:::{step} Remove the registration
If nothing uses the region anymore, delete the `register_oob_region` call. A startup WARNING about an optional orphan is the signal that a registration has gone stale.
:::{/step}
::::{/steps}

## When to mark a region optional

Mark a region `optional=True` only when it is *expected* to be absent from some layouts. The canonical case is chirp-ui's shell regions: an app using the full app-shell layout defines `breadcrumbs_oob` and `sidebar_oob`, but a bare custom layout may not — and that is fine.

```python
app.register_oob_region(
    "breadcrumbs_oob",
    target_id="chirpui-topbar-breadcrumbs",
    optional=True,   # shell region; bare custom layouts may omit it
)
```

:::{danger} Don't use `optional=True` to silence a typo
A misspelled block name or a forgotten `{% region %}` is a real bug. Marking it `optional` hides the error and the region silently disappears on every boosted navigation — exactly the silent DOM wipe fail-loud rendering exists to prevent.

```python
# WRONG — papering over a typo; the breadcrumbs silently never render
app.register_oob_region("breadcrums_oob", target_id="...", optional=True)

# RIGHT — fix the name (or define the block in the layout)
app.register_oob_region("breadcrumbs_oob", target_id="...")
```

The startup check tells the two apart: a non-optional orphan is an ERROR, an optional orphan is a WARNING. Use `optional` for the by-design absence, not the accident.
:::

## Catch it before users do

`app.check()` runs the `oob_registry` contract check at startup. For each registered block it walks every layout template and confirms at least one defines a matching block. An orphaned non-optional registration is an ERROR, so gate CI on it and a missing region fails the build, not production.

The canonical CI gate is the CLI — `chirp check` loads your app, runs every contract check, and exits non-zero on any ERROR (add `--warnings-as-errors` to fail on optional-orphan WARNINGs too):

```bash
chirp check myapp:app --warnings-as-errors
```

To assert the same thing from a pytest suite, call `app.check()` on a frozen app. It prints the report and raises `SystemExit(1)` on any ERROR (it returns `None` — it does not hand back a list of issues), so the test passes only when the contract is clean:

```python
import pytest

def test_app_contracts():
    app = make_app()  # build and freeze your app
    try:
        app.check()
    except SystemExit as exc:
        pytest.fail(f"app.check() reported contract errors (exit {exc.code})")
```

::::{dropdown} How severity is decided
:icon: shield

The check classifies each orphaned registration by whether it was marked optional:

:::{list-table}
:header-rows: 1

* - Registered as
  - Layout defines block?
  - Severity
  - Meaning
* - `optional=False`
  - yes
  - —
  - OK
* - `optional=False`
  - no
  - **ERROR**
  - Render would raise `BlockNotFoundError`
* - `optional=True`
  - yes
  - —
  - OK
* - `optional=True`
  - no
  - WARNING
  - Render skips the region; the registration may be stale
:::

`oob_registry` is a contract category like any other, so you can override its severity globally — for example to keep the older permissive behavior during a migration:

```python
from chirp.contracts.types import Severity

app.override_contract_severity("oob_registry", Severity.WARNING)
```

This is a migration escape hatch, not a supported long-term setting. See [[docs/quality/contracts-debugging/categories|contract categories and severities]] for the full list.
::::{/dropdown}

:::{dropdown} What `BlockNotFoundError` carries
:icon: bug

`BlockNotFoundError` multi-inherits from `ChirpError` and `KeyError`, so existing `except KeyError` handlers (including Kida's `render_block` contract) still catch it. The instance carries:

- `.template` — the layout template that was missing the block
- `.block` — the block name that wasn't found
- `.region` — the target DOM id, or `None`

See [[docs/reference/errors|error types]] for the full hierarchy.
:::

## What changed in 0.5

:::{changed} 0.5
Region updates that reference a missing block now raise `BlockNotFoundError` instead of emitting an empty OOB swap.
:::

Earlier versions silently swallowed a region update whose block didn't exist: the region was emitted with `html=""`, which wipes the target element's DOM content on every boosted navigation. Bugs like "my breadcrumbs keep disappearing" were impossible to trace from the server. Fail-loud rendering surfaces them at startup (the contract check) and at render time (the exception) instead.

:::{note} See also
- [[docs/build-apps/ui-extensions/app-shell|App shells]] — the `{% region %}` pattern and shell actions
- [[docs/build-apps/ui-extensions/ui-layers|UI layers & shell regions]] — the layout vocabulary and stable OOB element ids
- [[docs/build-apps/request-pipeline/render-plan|Render plan]] — inspect the render plan from middleware
- [[docs/quality/contracts-debugging/categories|Contract categories]] — every check `app.check()` runs
:::
