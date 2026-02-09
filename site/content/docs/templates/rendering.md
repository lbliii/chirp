---
title: Rendering
description: How Chirp renders templates via kida
draft: false
weight: 10
lang: en
type: doc
tags: [templates, rendering, kida]
keywords: [template, rendering, kida, context, environment]
category: guide
---

## Template Return Type

The `Template` return type tells Chirp to render a kida template with the given context:

```python
from chirp import Template

@app.route("/")
def index():
    return Template("index.html", title="Home", items=get_items())
```

The first argument is the template path relative to your `template_dir` (default: `templates/`). All keyword arguments become the template rendering context.

## Kida Integration

Chirp uses [kida](https://lbliii.github.io/kida) as its built-in template engine. The kida `Environment` is created during the app freeze phase and shared across all request handlers.

Key characteristics:

- **Same author** -- kida and chirp are built together. No integration seam.
- **AST-native** -- kida compiles templates to an AST, then to Python functions.
- **Block-aware** -- kida can render individual blocks, enabling fragment rendering.
- **Streaming** -- kida supports generator-based rendering for progressive HTML.
- **Thread-safe** -- kida's compiled templates are immutable. Safe under free-threading.

## Template Context

Every template automatically has access to:

- All keyword arguments passed to `Template(...)`
- Any globals registered via `@app.template_global()`
- The `request` object (injected automatically)

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

In the template:

```html
<h1>{{ user.name }}</h1>
{% if is_admin %}
  <span class="badge">Admin</span>
{% endif %}

{% for post in posts %}
  <article>{{ post.title }}</article>
{% endfor %}
```

## Template Inheritance

Kida supports Jinja2-style template inheritance:

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

## Auto-Reload in Debug Mode

When `AppConfig(debug=True)`, kida automatically reloads templates when they change on disk. No server restart needed during development.

In production (`debug=False`), templates are compiled once and cached.

## Next Steps

- [[docs/templates/fragments|Fragments]] -- Render named blocks independently
- [[docs/templates/filters|Filters]] -- Register custom template filters
- [[docs/streaming/html-streaming|Streaming HTML]] -- Progressive template rendering
