---
title: Fragments
description: Render named template blocks independently for htmx
draft: false
weight: 20
lang: en
type: doc
tags: [fragments, htmx, blocks, page, oob]
keywords: [fragment, page, oob, htmx, block, partial, render-block]
category: guide
---

## The Key Innovation

Most Python frameworks treat templates as "render a full page, return a string." Chirp can render a *named block* from a template independently, without rendering the rest of the page.

This is what makes htmx integration seamless. The browser requests a fragment, the server returns just the block it needs.

## Fragment

`Fragment` renders a specific block from a template:

```python
from chirp import Fragment

@app.route("/search")
def search(request: Request):
    results = do_search(request.query.get("q", ""))
    if request.is_fragment:
        return Fragment("search.html", "results_list", results=results)
    return Template("search.html", results=results)
```

Arguments:

:::{dropdown} Template path
:icon: file

Path to the template file (relative to `template_dir`).
:::

:::{dropdown} Block name
:icon: layers

The named block to render. Must exist in the template.
:::

:::{dropdown} Keyword arguments
:icon: database

Become the rendering context passed to the template.
:::

The template:

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

Full page request renders everything (base layout + content + results). Fragment request renders only `results_list` -- the `<div id="results">` and its contents.

## request.is_fragment

The `Request` object detects htmx requests automatically:

```python
request.is_fragment      # True if HX-Request header present
request.htmx_target      # Value of HX-Target header (e.g., "#results")
request.htmx_trigger     # Value of HX-Trigger header
request.is_history_restore  # True if htmx history restore
```

## Page

`Page` is syntactic sugar that auto-detects whether to return a full page or a fragment:

```python
from chirp import Page

@app.route("/search")
def search(request: Request):
    results = do_search(request.query.get("q", ""))
    return Page("search.html", "results_list", results=results)
```

If `request.is_fragment` is `True`, it renders the block. Otherwise, it renders the full template. This eliminates the `if/else` pattern.

## OOB (Out-of-Band Swaps)

Sometimes a single action needs to update multiple parts of the page. `OOB` sends a primary fragment plus additional out-of-band fragments in one response:

```python
from chirp import OOB, Fragment

@app.route("/cart/add", methods=["POST"])
async def add_to_cart(request: Request):
    item = await add_item(request)
    return OOB(
        Fragment("cart.html", "cart_items", items=get_cart()),
        Fragment("layout.html", "cart_count", count=cart_count()),
        Fragment("layout.html", "total_price", total=cart_total()),
    )
```

The first fragment is the main response. Additional fragments are appended with `hx-swap-oob="true"`, so htmx swaps them into the correct locations on the page.

## ValidationError

A specialized fragment for form validation errors. Returns a 422 status:

```python
from chirp import ValidationError

@app.route("/register", methods=["POST"])
async def register(request: Request):
    form = await request.form()
    errors = validate_registration(form)
    if errors:
        return ValidationError("register.html", "form_errors", errors=errors)
    # ... create user
```

This renders the `form_errors` block with a 422 status code, which htmx can handle with `hx-target-422` or a custom error handler.

## Block Availability

Only blocks that the template explicitly defines or overrides are available for fragment rendering. Inherited parent blocks that are not overridden in the child template are not available.

```html
{# child.html #}
{% extends "base.html" %}

{% block content %}
  {# This block IS available as a fragment #}
  {% block search_results %}
    <div id="results">...</div>
  {% endblock %}
{% endblock %}

{# The "nav" block from base.html is NOT available #}
{# unless child.html explicitly overrides it #}
```

## Next Steps

- [[docs/core-concepts/return-values|Return Values]] -- All return types
- [[docs/streaming/server-sent-events|Server-Sent Events]] -- Push fragments in real-time
- [[docs/tutorials/htmx-patterns|htmx Patterns]] -- Common fragment patterns
