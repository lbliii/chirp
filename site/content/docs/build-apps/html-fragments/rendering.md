---
title: Rendering
description: Return a full HTML page from a template with the Template return type
draft: false
weight: 10
lang: en
type: doc
tags: [templates, rendering, kida]
keywords: [template, rendering, kida, context, environment]
category: guide
---

## Overview

`Template` is the simplest return type: it renders a full HTML page from a [[docs/build-apps/html-fragments/kida-integration|kida]] template plus the context you pass it. Reach for it when a handler should return a complete page — a browser navigation, or any server-rendered view that isn't a fragment swap or a stream.

```python
from chirp import Template

@app.route("/")
def index():
    return Template("index.html", title="Home", items=get_items())
```

The first argument is the template path relative to your `template_dir` (default `templates/`). Every keyword argument becomes a variable in the template's render context.

## When to reach for it

`Template` is the base case the other return types build on. Learn this one first.

:::{note}
- **`Template`** renders the whole page, every time. Use it for browser navigations and views that are always full pages.
- **`Fragment`** renders one named block of the same template — for an htmx swap that replaces part of an already-loaded page. See [[docs/build-apps/html-fragments/fragments|Fragments]].
- **`Page`** auto-picks page-vs-fragment by inspecting the request, so one handler serves both. See [[docs/about/core-concepts/return-values|return types]].

`Suspense` and `Stream` render the same template progressively. See [[docs/build-apps/streaming-updates/html-streaming|Streaming HTML]].
:::

## Template context

Every template automatically has access to:

- All keyword arguments passed to `Template(...)`.
- Any globals registered with `@app.template_global()` (see [[docs/build-apps/html-fragments/filters|custom filters and globals]]).
- `current_path` (the request path, set to `request.path`) — auto-injected when you don't pass it yourself.

Chirp does **not** put the `request` object in the template context. To use request data in a template, take a typed `Request` parameter and pass the values you need explicitly:

```python
from chirp import Request, Template

@app.route("/dashboard")
def dashboard(request: Request):
    return Template("dashboard.html", is_htmx=request.is_htmx)
```

```python
@app.route("/users/{id:int}")
def user_profile(id: int):
    user = get_user(id)
    return Template("profile.html",
        user=user,
        posts=get_posts(user.id),
        is_admin=user.role == "admin",
    )
```

In `profile.html`:

```html
<h1>{{ user.name }}</h1>
{% if is_admin %}
  <span class="badge">Admin</span>
{% endif %}

{% for post in posts %}
  <article>{{ post.title }}</article>
{% endfor %}
```

:::{note}
With `AppConfig(debug=True)`, kida reloads templates from disk on change — no server restart while you edit. In production (`debug=False`), templates compile once and stay cached.
:::

## Composing a layout

A page template can pull shared chrome — `<head>`, nav, footer — from a base template. For standalone templates, kida supports `{% extends %}` inheritance:

```html
{# base.html #}
<!DOCTYPE html>
<html>
<head><title>{% block title %}My App{% endblock %}</title></head>
<body>
  <nav>{% block nav %}...{% endblock %}</nav>
  <main>{% block content %}{% endblock %}</main>
</body>
</html>
```

```html
{# page.html #}
{% extends "base.html" %}

{% block title %}{{ title }} - My App{% endblock %}

{% block content %}
  <h1>{{ title }}</h1>
  <p>{{ description }}</p>
{% endblock %}
```

:::{warning}
`{% extends %}` is for standalone templates you render directly. Mounted, filesystem-routed pages use **layout composition**, not inheritance: Chirp injects the page's HTML into the layout's `{% block content %}` and the page template **cannot** override sibling layout blocks like `nav` or `head_extra`. Don't reach for `{% extends %}` to compose a mounted-page layout — see [[docs/build-apps/html-fragments/layout-patterns|layout composition]].
:::

::::{dropdown} Advanced: how kida renders
Chirp uses [[docs/build-apps/html-fragments/kida-integration|kida]] as its built-in template engine. The kida `Environment` is created during the app freeze phase and shared across every request handler.

- **AST-native** — kida compiles each template to an AST, then to a Python function.
- **Block-aware** — kida can render an individual named block, which is what makes `Fragment` rendering possible.
- **Streaming** — kida supports generator-based rendering for progressive HTML.
- **Thread-safe** — compiled templates are immutable, so rendering is safe under free-threading.

You don't construct the `Environment` yourself; Chirp builds and freezes it for you.
::::{/dropdown}

:::{note} See also
- [[docs/build-apps/html-fragments/fragments|Fragments]] — render one named block for an htmx swap
- [[docs/about/core-concepts/return-values|Return types]] — pick the right return type for the job
- [[docs/build-apps/html-fragments/layout-patterns|Layout composition]] — compose layouts for mounted pages
- [[docs/build-apps/html-fragments/filters|Filters and globals]] — register custom template helpers
:::
