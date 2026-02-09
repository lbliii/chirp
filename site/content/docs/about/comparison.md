---
title: Comparison
description: Chirp vs Flask, FastAPI, and Django
draft: false
weight: 30
lang: en
type: doc
tags: [comparison, flask, fastapi, django]
keywords: [comparison, flask, fastapi, django, htmx, fragments, streaming]
category: explanation
---

## The Landscape

Flask (2010), Django (2005), and FastAPI (2018) were designed for a different web. Each makes assumptions that don't match where the web platform is in 2026.

## Feature Comparison

| Feature | Chirp | Flask | FastAPI | Django |
|---------|-------|-------|---------|--------|
| **Fragment rendering** | Built-in | No | No | No |
| **Streaming HTML** | Built-in | No | Manual | No |
| **Server-Sent Events** | Built-in | Extension | Manual | Channels |
| **htmx integration** | First-class | Extension | Manual | Extension |
| **Typed contracts** | `app.check()` | No | OpenAPI | No |
| **Template engine** | Kida (built-in) | Jinja2 (plugin) | None | DTL (built-in) |
| **Free-threading** | Native | No | No | No |
| **ASGI** | Native | Via adapter | Native | Via ASGI handler |
| **Type safety** | Strict (ty clean) | Partial | Strong | Partial |

## vs Flask

Flask got the surface right. Chirp starts from the same place -- decorators, return values, simple setup.

```python
# Flask
@app.route("/")
def index():
    return render_template("index.html", title="Home")

# Chirp
@app.route("/")
def index():
    return Template("index.html", title="Home")
```

Where Chirp diverges:

- **Fragments**: Flask can't render a named block from a template. You need separate partial templates and manual htmx wiring. Chirp renders any block independently.
- **Streaming**: Flask's `Response(generate())` is manual chunked encoding. Chirp's `Stream` integrates with kida's streaming renderer.
- **Immutability**: Flask's `request` is a thread-local proxy. Chirp's `Request` is a frozen dataclass.
- **Configuration**: Flask uses a dict (`app.config["SECRET_KEY"]`). Chirp uses a frozen dataclass with IDE autocomplete.

**When to use Flask**: Existing Flask apps, extensive ecosystem of extensions, WSGI deployment.

## vs FastAPI

FastAPI assumes you serve JSON to a JavaScript frontend. It has no template story.

```python
# FastAPI
@app.get("/users/{id}")
async def get_user(id: int):
    return {"id": id, "name": "Alice"}

# Chirp
@app.route("/users/{id:int}")
def get_user(id: int):
    return Template("user.html", user=get_user(id))
```

Where Chirp diverges:

- **HTML-first**: Chirp is designed to serve HTML. FastAPI is designed to serve JSON.
- **Templates**: Chirp has kida built in with fragment rendering. FastAPI has `Jinja2Templates` as an afterthought.
- **Validation**: FastAPI uses Pydantic for request validation. Chirp uses form validation rules and typed path parameters.
- **OpenAPI**: FastAPI auto-generates OpenAPI specs. Chirp validates hypermedia contracts instead.

**When to use FastAPI**: JSON APIs, Pydantic-heavy data validation, OpenAPI documentation.

## vs Django

Django is a batteries-included framework. Chirp is not.

Where Chirp diverges:

- **Scope**: Django includes ORM, admin, auth, forms, migrations, email, caching. Chirp includes routing, templates, middleware, and SSE.
- **Templates**: Django Template Language cannot render individual blocks. Chirp + kida can.
- **Real-time**: Django requires Channels for WebSocket/SSE. Chirp has SSE built in.
- **Size**: Django is ~300k lines. Chirp is ~5k lines (53 modules).

**When to use Django**: Full-featured applications, tight deadlines, admin interfaces, established teams.

## When to Use Chirp

Chirp is designed for:

- **htmx-driven applications** where the server renders HTML fragments
- **Real-time dashboards** with streaming HTML and SSE
- **Modern web apps** that leverage the browser's native capabilities
- **Python 3.14t** applications that want true free-threading
- **Developers who want to own their stack** -- compose exactly what you need

Chirp is *not* designed for:

- JSON APIs (use FastAPI)
- Full-featured apps with admin panels (use Django)
- Apps that need WSGI compatibility (use Flask)
- Teams that need maximum ecosystem support (use Flask or Django)

## Next Steps

- [[docs/about/philosophy|Philosophy]] -- Why Chirp makes these choices
- [[docs/get-started/quickstart|Quickstart]] -- Try it yourself
- [[docs/tutorials/coming-from-flask|Coming from Flask]] -- Migration guide
