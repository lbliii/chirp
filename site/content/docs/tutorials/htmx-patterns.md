---
title: htmx Patterns
description: Common htmx + Chirp patterns for building interactive apps
draft: false
weight: 20
lang: en
type: doc
tags: [tutorial, htmx, patterns, fragments]
keywords: [htmx, patterns, search, inline-edit, infinite-scroll, modal, fragments]
category: tutorial
---

## Overview

Chirp's fragment rendering makes htmx integration seamless. These patterns demonstrate common interactive UI features with zero client-side JavaScript.

## Live Search

Search that updates results as you type:

**Template** (`templates/search.html`):

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

**Handler**:

```python
@app.route("/search")
def search(request: Request):
    q = request.query.get("q", "")
    results = do_search(q) if q else []

    if request.is_fragment:
        return Fragment("search.html", "results", results=results)
    return Template("search.html", results=results)
```

The browser renders the full page on first load. As the user types, htmx sends requests and Chirp responds with just the `results` block.

## Click to Edit

Inline editing that swaps between display and edit views:

**Template** (`templates/contact.html`):

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

**Handlers**:

```python
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

Three handlers, zero JavaScript. Each returns a fragment that htmx swaps into place.

## Infinite Scroll

Load more content as the user scrolls:

**Template** (`templates/feed.html`):

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

**Handler**:

```python
PAGE_SIZE = 20

@app.route("/feed")
def feed(request: Request):
    page = int(request.query.get("page", "1"))
    items = get_items(page=page, size=PAGE_SIZE)
    has_more = len(items) == PAGE_SIZE

    ctx = dict(items=items, has_more=has_more, next_page=page + 1)

    if request.is_fragment:
        return Fragment("feed.html", "feed_items", **ctx)
    return Template("feed.html", **ctx)
```

The `hx-trigger="revealed"` attribute fires when the element scrolls into view. htmx fetches the next page and appends it with `hx-swap="beforeend"`.

## Delete with Confirmation

Delete an item with a confirmation step:

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
    return ""  # Empty response removes the element
```

## Form Validation

Submit a form and show inline errors:

```html
<form hx-post="/register" hx-target="#form-errors" hx-swap="innerHTML">
  <input name="name" placeholder="Name">
  <input name="email" placeholder="Email">
  <input name="password" type="password" placeholder="Password">
  <div id="form-errors"></div>
  <button type="submit">Register</button>
</form>
```

```python
@app.route("/register", methods=["POST"])
async def register(request: Request):
    form = await request.form()
    errors = validate(form)
    if errors:
        return ValidationError("register.html", "form_errors", errors=errors)
    create_user(form)
    return Redirect("/welcome")
```

## Real-Time Notifications

Push notifications via SSE:

```html
<div hx-ext="sse" sse-connect="/notifications" sse-swap="message">
  <div id="notifications">
    <!-- SSE fragments are swapped in here -->
  </div>
</div>
```

```python
@app.route("/notifications")
async def notifications():
    async def stream():
        async for event in notification_bus.subscribe():
            yield Fragment("components/notification.html",
                message=event.message,
                time=event.timestamp,
            )
    return EventStream(stream())
```

## OOB Multi-Update

Update multiple page sections in one request:

```python
@app.route("/cart/add", methods=["POST"])
async def add_to_cart(request: Request):
    item = await add_item(request)
    return OOB(
        Fragment("cart.html", "cart_items", items=get_cart()),
        Fragment("layout.html", "cart_badge", count=cart_count()),
    )
```

The first fragment is the main swap target. Additional fragments use `hx-swap-oob` to update other parts of the page.

## Next Steps

- [[docs/templates/fragments|Fragments]] -- Fragment rendering in depth
- [[docs/streaming/server-sent-events|Server-Sent Events]] -- Real-time patterns
- [[docs/tutorials/coming-from-flask|Coming from Flask]] -- Migration guide
