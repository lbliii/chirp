---
title: Fragments
description: Render a single named template block on its own, so htmx can swap just the piece of the DOM it asked for.
draft: false
weight: 20
lang: en
type: doc
tags: [fragments, htmx, blocks, page, oob]
keywords: [fragment, page, oob, htmx, block, partial, render-block, content negotiation]
category: guide
---

## What a fragment is

A fragment is a single named block from a template, rendered on its own — without the surrounding page. That is what lets an htmx request swap just the piece of the DOM it asked for: the browser requests a target, Chirp returns only that block.

This page covers the return types that produce fragments:

- `Fragment` — render one named block.
- `Page` — auto-pick fragment vs. full page based on the request.
- `OOB` — one response, several out-of-band swaps.
- `ValidationError` — a 422 form fragment for a failed validation.

If you already know htmx fragments and just want the Chirp mapping, jump to the [example](#fragment) below. The return type is the intent — for the full picture of every return type, see [[docs/about/core-concepts/return-values|the return-type decision tree]].

## Fragment

`Fragment` renders one named block from a template. The handler decides whether the request wants a fragment; the template stays the same single file that also serves the full page.

:::{tab-set}
:::{tab-item} Handler (page.py)
```python
from chirp import Fragment, Request, Template

@app.route("/search")
def search(request: Request):
    results = do_search(request.query.get("q", ""))
    if request.is_narrow_fragment:
        return Fragment("search.html", "results_list", results=results)
    return Template("search.html", results=results)
```
:::{/tab-item}
:::{tab-item} Template (search.html)
```html
{% extends "base.html" %}

{% block content %}
  <input type="search" hx-get="/search" hx-target="#results" name="q">

  {% block results_list %}
    <div id="results">
      {% for item in results %}
        <div class="result">{{ item.title }}</div>
      {% endfor %}
    </div>
  {% endblock %}
{% endblock %}
```
:::{/tab-item}
:::{/tab-set}

A full-page request renders everything (base layout + content + results). A narrow htmx request renders only `results_list` — the `<div id="results">` and its contents.

`Fragment(template, block, **context)` takes the template path (relative to `template_dir`), the named block to render, and keyword arguments that become the rendering context. Pass `target="dom-id"` to override the swap target for an OOB or SSE delivery.

## Detecting htmx requests

The `Request` object exposes typed properties for reacting to htmx requests. Use `is_narrow_fragment` for "should I return just the block?" — it is `True` only for a narrow fragment swap, and `False` for boosted navigations and history restores, which need full page content.

:::{warning}
`request.is_fragment` is deprecated and emits a `DeprecationWarning` on every access. It is `True` for *any* htmx request, including boosted navigations and history restores that actually need the full page — that ambiguity is the bug. Use `request.is_htmx` (any htmx request) or `request.is_narrow_fragment` (narrow swap only) instead. The old name still appears in older codebases; do not copy it forward.
:::

:::{list-table}
:header-rows: 1

* - Property
  - `True` when
* - `request.is_htmx`
  - Any htmx request (`HX-Request` header present).
* - `request.is_narrow_fragment`
  - A narrow htmx swap — excludes boosted navigations, history restores, and htmx 4 body-level `full` requests.
* - `request.htmx_target_id`
  - Normalizes `div#results`, `#results`, or legacy `results` to `results`; malformed or tag-only values return `None`.
* - `request.htmx_source_id`
  - Returns the id parsed from htmx 4 `HX-Source: tag#id`, or `None`.
* - `request.htmx_request_type`
  - Validated htmx 4 `full` / `partial` metadata, or `None`.
* - `request.is_history_restore`
  - htmx is restoring from history (cache miss on back/forward).
:::

:::{note} See also
- [[docs/build-apps/pages-navigation/request-response|request detection in detail]] — the full set of `request.htmx.*` properties.
:::

## Page

Most htmx-reachable routes do not need the `if/else`. `Page` is the auto-negotiated form: it inspects the request and renders the right thing.

```python
from chirp import Page, Request

@app.route("/search")
def search(request: Request):
    results = do_search(request.query.get("q", ""))
    return Page("search.html", "results_list", results=results)
```

`Page` does not collapse to a simple "fragment or full page" boolean. It renders:

- the **full template** for normal browser navigations and htmx history restores;
- the **named fragment block** for narrow htmx requests;
- a wider **page block** for boosted navigations, when you supply one (below).

::::{dropdown} Boosted navigation: a wider fragment root
When a route is reachable by both narrow swaps and `hx-boost` navigation, the narrow block is often too small to stand alone as a page body. Pass `page_block_name` so boosted navigations get a fragment-safe root while explicit swaps still target the narrow block:

```python
return Page(
    "search.html",
    "results_list",
    page_block_name="page_root",
    results=results,
)
```

- `results_list` stays the narrow fragment target for explicit swaps.
- `page_root` becomes the fragment-safe root for boosted navigation.

For mounted page-directory templates that follow Chirp's conventional `page_root` / `page_content` blocks, `Page.mounted("dashboard/page.html", **ctx)` wires both names for you.
::::{/dropdown}

## OOB (out-of-band swaps)

Sometimes one action updates several parts of the page. `OOB` sends a primary fragment plus additional out-of-band fragments in a single response.

```python
from chirp import OOB, Fragment, Request

@app.route("/cart/add", methods=["POST"])
async def add_to_cart(request: Request):
    item = await add_item(request)
    return OOB(
        Fragment("cart.html", "cart_items", items=get_cart()),
        Fragment("layout.html", "cart_count", count=cart_count()),
        Fragment("layout.html", "total_price", total=cart_total()),
    )
```

The first fragment is the primary swap target. Each additional fragment is rendered with `hx-swap-oob="true"` and an `id` matching its target (the block name by default, or `Fragment(..., target="id")`), so htmx swaps them into the right places.

:::{warning}
OOB region updates must resolve to a block that exists in the target template, or Chirp raises `BlockNotFoundError` rather than emitting an empty swap that silently wipes live DOM content. `app.check()` enforces this at startup. See [[docs/quality/contracts-debugging/oob-registry|the OOB region registry]] for registering and validating shell regions.
:::

## ValidationError

`ValidationError` bundles the common htmx form pattern: validate server-side, re-render the form fragment with errors, and return a **422** status so htmx knows to swap the error content.

```python
from chirp import ValidationError, Request
from chirp.validation import validate, required, email

RULES = {"email": [required, email]}

@app.route("/register", methods=["POST"])
async def register(request: Request):
    form = await request.form()
    result = validate(form, RULES)
    if not result:
        return ValidationError(
            "register.html", "form_errors",
            errors=result.errors, form=form,
        )
    # ... create the user
```

The `form_errors` block re-renders with a 422 status. Chirp's htmx 4 preview
swaps 4xx HTML by policy, so use the form's ordinary local `hx-target`. Pass
`retarget="#error-banner"` to add an `HX-Retarget` header when errors should
land in a different element than the trigger. Htmx 2 applications retain their
configured response-handling behavior.

:::{note} See also
- [[docs/build-apps/forms-data/forms-validation|Forms & validation]] — the full `validate()` API, validator functions, and form patterns.
:::

## Where fragments come from

Chirp discovers block names, regions, and dependencies from the template at build time — it never hard-codes which blocks exist. That is what backs fragment validation in `app.check()` and automatic OOB region discovery. You render blocks; you do not register them.

::::{dropdown} How Chirp finds blocks
Chirp uses Kida's `template_metadata()` to introspect each template's AST at build time. Block names, regions, and dependencies come from the AST, which enables:

- **Validation** — `Fragment`/`Page` block names are checked before render.
- **OOB discovery** — blocks named `*_oob` are discovered automatically for app shells.
- **Layout contracts** — each block's `depends_on` and `cache_scope` drive when OOB regions re-render.

This is build-time machinery you do not call directly. See [[docs/build-apps/html-fragments/kida-integration|Kida integration]] for the full flow.
::::{/dropdown}

:::{note} See also
Fragments live inside layouts and reusable blocks — those topics have their own homes:

- [[docs/build-apps/html-fragments/layout-patterns|Layout patterns]] — block inheritance, boosted-root layouts, extension blocks, and shell OOB regions.
- [[docs/build-apps/html-fragments/fragment-blocks|Fragment blocks]] — the `{% fragment %}` block directive.
- [[docs/build-apps/html-fragments/kida-integration|Kida integration]] — how Chirp reads templates and maps shell regions to DOM ids.
:::

## Next step

Push fragments to the browser in real time with [[docs/build-apps/streaming-updates/server-sent-events|Server-Sent Events]] — the same named blocks, streamed instead of swapped on request.

:::{related}
:::
