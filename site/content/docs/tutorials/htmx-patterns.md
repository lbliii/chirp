---
title: htmx Patterns
description: The fast mapping from raw hx-* attributes to Chirp's return types — live search, click-to-edit, infinite scroll, delete, and reorder, each a copy-paste template-plus-handler pair.
draft: false
weight: 20
lang: en
type: doc
tags: [tutorial, htmx, patterns, fragments]
keywords: [htmx, patterns, search, inline-edit, infinite-scroll, delete, reorder, fragments]
category: tutorial
---

## Overview

If you already know htmx, this page is the fast mapping from raw `hx-*` attributes
to Chirp's return types. Each pattern is a self-contained template-plus-handler
pair you can copy: live search, click-to-edit, infinite scroll, delete, reorder,
and inline validation.

The recurring move is the one Chirp is built around: your handler returns a
[[docs/build-apps/html-fragments/fragments|Fragment]] (one named template block)
and htmx swaps it into place. No client JavaScript, no JSON.

When a route serves both a full page (browser navigation) **and** a fragment
(htmx swap), return a [[docs/about/core-concepts/return-values|Page]] and let
Chirp negotiate from the request headers, rather than branching on request flags
by hand. `Page("search.html", "results", ...)` renders the full template for a
browser and just the `results` block for an htmx request — one return, no
boilerplate.

:::{note} See also
- [[docs/about/core-concepts/return-values|Return values]] — the decision tree for `Template` vs `Fragment` vs `Page`
- [[docs/examples/returns-gallery|Returns gallery]] — every return type, runnable
:::

## Live search

Search that updates results as you type. The page loads as a full document; each
keystroke fetches just the `results` block.

:::{tab-set}
:::{tab-item} Template
`templates/search.html`:

```html
{% extends "base.html" %}

{% block content %}
  <h1>Search</h1>
  <input type="search" name="q" placeholder="Search..."
         hx-get="/search" hx-target="#results"
         hx-trigger="input changed delay:300ms">

  {% block results %}
    <div id="results">
      {% for item in results %}
        <div class="result">
          <h3>{{ item.title }}</h3>
          <p>{{ item.description }}</p>
        </div>
      {% endfor %}
      {% if not results %}
        <p class="empty">No results found.</p>
      {% endif %}
    </div>
  {% endblock %}
{% endblock %}
```
:::{/tab-item}
:::{tab-item} Handler
```python
from chirp import Page, Request

@app.route("/search")
def search(request: Request):
    q = request.query.get("q", "")
    results = do_search(q) if q else []
    return Page("search.html", "results", results=results)
```
:::{/tab-item}
:::{/tab-set}

`Page` inspects the request: a browser navigation gets the full `search.html`
page, while htmx's keystroke requests get only the `results` block swapped into
`#results`.

## Click to edit

Inline editing that swaps between a display view and an edit form. The display
block and the edit block live in one template; three handlers swap between them.

:::{tab-set}
:::{tab-item} Template
`templates/contact.html`:

```html
{% block contact_display %}
  <div id="contact-{{ contact.id }}" class="contact">
    <span>{{ contact.name }} — {{ contact.email }}</span>
    <button hx-get="/contacts/{{ contact.id }}/edit"
            hx-target="#contact-{{ contact.id }}"
            hx-swap="outerHTML">
      Edit
    </button>
  </div>
{% endblock %}

{% block contact_edit %}
  <form id="contact-{{ contact.id }}" class="contact editing"
        hx-put="/contacts/{{ contact.id }}"
        hx-target="#contact-{{ contact.id }}"
        hx-swap="outerHTML">
    <input name="name" value="{{ contact.name }}">
    <input name="email" value="{{ contact.email }}">
    <button type="submit">Save</button>
    <button hx-get="/contacts/{{ contact.id }}"
            hx-target="#contact-{{ contact.id }}"
            hx-swap="outerHTML">
      Cancel
    </button>
  </form>
{% endblock %}
```
:::{/tab-item}
:::{tab-item} Handlers
```python
from chirp import Fragment, Request

@app.route("/contacts/{id:int}")
def show_contact(id: int):
    contact = get_contact(id)
    return Fragment("contact.html", "contact_display", contact=contact)

@app.route("/contacts/{id:int}/edit")
def edit_contact(id: int):
    contact = get_contact(id)
    return Fragment("contact.html", "contact_edit", contact=contact)

@app.route("/contacts/{id:int}", methods=["PUT"])
async def update_contact(request: Request, id: int):
    form = await request.form()
    contact = save_contact(id, name=form["name"], email=form["email"])
    return Fragment("contact.html", "contact_display", contact=contact)
```
:::{/tab-item}
:::{/tab-set}

These three routes return a bare `Fragment` because they are reached only by
htmx swaps, never by direct browser navigation. If a route is also a landing URL
someone could type or bookmark, return `Page` instead so the full document
renders for a cold load.

## Infinite scroll

Load more content as the user scrolls. A sentinel element fires `revealed` when
it enters the viewport, fetches the next page, and appends it.

:::{tab-set}
:::{tab-item} Template
`templates/feed.html`:

```html
{% block feed_items %}
  <div id="feed">
    {% for item in items %}
      <article class="feed-item">
        <h3>{{ item.title }}</h3>
        <p>{{ item.summary }}</p>
      </article>
    {% endfor %}

    {% if has_more %}
      <div hx-get="/feed?page={{ next_page }}"
           hx-target="#feed"
           hx-swap="beforeend"
           hx-trigger="revealed">
        <span class="loading">Loading more...</span>
      </div>
    {% endif %}
  </div>
{% endblock %}
```
:::{/tab-item}
:::{tab-item} Handler
```python
from chirp import Page, Request

PAGE_SIZE = 20

@app.route("/feed")
def feed(request: Request):
    page = int(request.query.get("page", "1"))
    items = get_items(page=page, size=PAGE_SIZE)
    has_more = len(items) == PAGE_SIZE
    return Page(
        "feed.html", "feed_items",
        items=items, has_more=has_more, next_page=page + 1,
    )
```
:::{/tab-item}
:::{/tab-set}

`hx-trigger="revealed"` fires when the sentinel scrolls into view; `Page`
serves the full feed to a browser and just the `feed_items` block to the
scroll-triggered htmx request.

## Delete with confirmation

Delete an item after a confirmation prompt. `hx-confirm` shows the browser
dialog; the handler removes the row by returning nothing.

```html
<button hx-delete="/items/{{ item.id }}"
        hx-target="#item-{{ item.id }}"
        hx-swap="outerHTML"
        hx-confirm="Delete this item?">
  Delete
</button>
```

```python
@app.route("/items/{id:int}", methods=["DELETE"])
def delete_item(id: int):
    remove_item(id)
    return ""
```

:::{note}
Returning an empty string swaps the target's `outerHTML` with nothing — htmx
removes the element. This is the idiomatic way to delete a row: there is no
"delete" return type, the empty body *is* the deletion.
:::

## Reorder list (drag and drop)

Reorder items with native HTML5 drag and drop — no Sortable.js. A hidden form
carries the source and target indices; on drop, Alpine populates it and calls
`htmx.trigger(form, 'submit')`. The handler returns a `Fragment` with the
reordered list, and `hx-select` extracts the target element from the response.

This pattern uses the [chirp-ui](https://github.com/lbliii/chirp-ui)
`sortable_list` / `sortable_item` macros (`pip install chirp[ui]`).

:::{tab-set}
:::{tab-item} Template
```html
{% imports %}
  {% from "chirpui/sortable_list.html" import sortable_list, sortable_item %}
{% end %}

<div id="recipe-content">
  <form id="reorder-form" method="post" action="/reorder"
        hx-post="/reorder" hx-target="#recipe-content"
        hx-select="#recipe-content" hx-swap="outerHTML"
        style="display:none">
    {{ csrf_field() }}
    <input type="hidden" name="from_idx" value="">
    <input type="hidden" name="to_idx" value="">
  </form>

  {% call sortable_list() %}
    {% for step in steps %}
    {% call sortable_item(attrs_unsafe='draggable="true"') %}
      {{ step.instruction }}
    {% end %}
    {% end %}
  {% end %}
</div>
```
:::{/tab-item}
:::{tab-item} Handler
```python
from chirp import Fragment, Request

@app.route("/reorder", methods=["POST"])
async def reorder_route(request: Request):
    form = await request.form()
    from_idx = int(form.get("from_idx", 0))
    to_idx = int(form.get("to_idx", 0))
    reorder_steps(from_idx, to_idx)
    return Fragment("page.html", "recipe_content", steps=get_steps())
```
:::{/tab-item}
:::{/tab-set}

*Source: [`examples/chirpui/sortable_reorder/app.py`](https://github.com/lbliii/chirp/blob/main/examples/chirpui/sortable_reorder/app.py).*

:::{dropdown} Advanced: the drag-and-drop Alpine wiring
The drop handler tracks a source index in the list's `dataset`, uses a per-item
`overCount` to keep the drop indicator flicker-free, and triggers the hidden
form on drop. The full wiring lives in chirp-ui's
[DND-FRAGMENT-ISLAND](https://github.com/lbliii/chirp-ui/blob/main/docs/DND-FRAGMENT-ISLAND.md)
guide; the `sortable_reorder` example above ships the complete, runnable version.
:::{/dropdown}

## Form validation

Submit a form and re-render it with inline errors on failure, or redirect on
success.

```html
<form hx-post="/register" hx-target="#form-errors" hx-swap="innerHTML">
  {{ csrf_field() }}
  <input name="name" placeholder="Name">
  <input name="email" placeholder="Email">
  <input name="password" type="password" placeholder="Password">
  <div id="form-errors"></div>
  <button type="submit">Register</button>
</form>
```

```python
from chirp import ValidationError, hx_redirect, Request

@app.route("/register", methods=["POST"])
async def register(request: Request):
    form = await request.form()
    errors = validate(form)
    if errors:
        return ValidationError("register.html", "form_errors", errors=errors)
    create_user(form)
    return hx_redirect("/welcome")
```

:::{tip}
`hx_redirect("/welcome")` is the safer default for redirects. The same form
works whether it posts normally or via htmx — `hx_redirect` issues an
`HX-Redirect` header for htmx requests and a standard `303` HTTP redirect
otherwise, so you never lose the no-JavaScript fallback.
:::

For validation rules, error shapes, and the full re-render flow, see
[[docs/build-apps/forms-data/forms-validation|forms and validation]].

## Real-time notifications

Push updates to the page after it loads with Server-Sent Events. The browser
subscribes once; the handler streams `Fragment`s as events arrive.

```html
<div hx-ext="sse" sse-connect="/notifications" sse-swap="message">
  <div id="notifications">
    <!-- SSE fragments are swapped in here -->
  </div>
</div>
```

```python
from chirp import EventStream, Fragment

@app.route("/notifications")
async def notifications():
    async def stream():
        async for event in notification_bus.subscribe():
            yield Fragment("components/notification.html", "notification",
                message=event.message,
                time=event.timestamp,
            )
    return EventStream(stream())
```

:::{note} See also
SSE is its own surface with backpressure, reconnection, and scoping concerns
this page does not cover.
- [[docs/build-apps/streaming-updates/server-sent-events|Server-Sent Events]] — the full SSE guide
- [[docs/examples/sse|SSE example]] — a runnable notifications feed
:::

## OOB multi-update

Update several page sections in one response. The first `Fragment` is the main
swap target; each additional `Fragment` carries `hx-swap-oob` to patch a
different element.

```python
from chirp import OOB, Fragment, Request

@app.route("/cart/add", methods=["POST"])
async def add_to_cart(request: Request):
    await add_item(request)
    return OOB(
        Fragment("cart.html", "cart_items", items=get_cart()),
        Fragment("layout.html", "cart_badge", count=cart_count()),
    )
```

:::{note} See also
Registering OOB regions makes their targets contract-checked at startup, so a
missing block fails loudly instead of silently wiping live DOM.
- [[docs/quality/contracts-debugging/oob-registry|OOB registry]] — register and validate OOB swap targets
:::

## Event delegation for dynamic content

:::{warning}
`hx-on::click` and similar inline handlers bind once, when the DOM is parsed.
Content that arrives later via htmx swaps (SSE, OOB, fragments) gets **no**
handlers — clicks on swapped-in elements silently do nothing.
:::

Use event delegation: attach one listener to `document` or a stable parent, and
check whether the event target matches your selector.

```html
<script>
document.addEventListener('click', function(e) {
  var btn = e.target.closest('.copy-btn');
  if (btn) {
    var wrap = btn.closest('[data-copy-text]');
    if (wrap) {
      navigator.clipboard.writeText(wrap.dataset.copyText || '');
      btn.textContent = 'Copied!';
      setTimeout(function() { btn.textContent = 'Copy'; }, 1500);
    }
  }
});
</script>
```

The same pattern works for toggles, compare switches, and any interactive
element inside SSE- or fragment-swapped content. Chirp ships this for you:
`AppConfig(delegation=True)` wires delegated copy-button and compare-switch
handlers for swapped content. See the [[docs/examples/rag-demo|RAG demo]].

## Next steps

- [[docs/build-apps/html-fragments/fragments|Fragments]] — fragment rendering in depth
- [[docs/build-apps/streaming-updates/server-sent-events|Server-Sent Events]] — real-time patterns
- [[docs/tutorials/coming-from-flask|Coming from Flask]] — migration guide

:::{related}
:::
