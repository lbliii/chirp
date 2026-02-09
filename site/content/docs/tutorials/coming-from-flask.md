---
title: Coming from Flask
description: Translate your Flask knowledge to Chirp
draft: false
weight: 10
lang: en
type: doc
tags: [tutorial, flask, migration]
keywords: [flask, migration, translate, side-by-side, comparison]
category: tutorial
---

## Overview

If you know Flask, you already know 80% of Chirp. This guide maps Flask concepts to their Chirp equivalents.

## App Setup

:::{tab-set}
:::{tab-item} Flask
```python
from flask import Flask

app = Flask(__name__)
app.config["SECRET_KEY"] = "secret"
```
:::{/tab-item}

:::{tab-item} Chirp
```python
from chirp import App, AppConfig

config = AppConfig(secret_key="secret")
app = App(config=config)
```
:::{/tab-item}
:::{/tab-set}

Chirp uses a frozen dataclass instead of a dict. No `app.config["SCRET_KEY"]` typos.

## Routes

:::{tab-set}
:::{tab-item} Flask
```python
@app.route("/users/<int:id>")
def user(id):
    return render_template("user.html", user=get_user(id))
```
:::{/tab-item}

:::{tab-item} Chirp
```python
@app.route("/users/{id:int}")
def user(id: int):
    return Template("user.html", user=get_user(id))
```
:::{/tab-item}
:::{/tab-set}

Differences:
- Path parameters use `{name:type}` instead of `<type:name>`
- Return `Template(...)` instead of calling `render_template()`
- Type annotations on handler parameters

## Request Access

:::{tab-set}
:::{tab-item} Flask
```python
from flask import request

@app.route("/search")
def search():
    q = request.args.get("q", "")
    return render_template("search.html", q=q)
```
:::{/tab-item}

:::{tab-item} Chirp
```python
from chirp import Request

@app.route("/search")
def search(request: Request):
    q = request.query.get("q", "")
    return Template("search.html", q=q)
```
:::{/tab-item}
:::{/tab-set}

Differences:
- `request` is a parameter, not a global import
- `request.query` instead of `request.args`
- The request is frozen (immutable)

## JSON Responses

:::{tab-set}
:::{tab-item} Flask
```python
from flask import jsonify

@app.route("/api/users")
def api_users():
    return jsonify({"users": get_all_users()})
```
:::{/tab-item}

:::{tab-item} Chirp
```python
@app.route("/api/users")
def api_users():
    return {"users": get_all_users()}
```
:::{/tab-item}
:::{/tab-set}

No `jsonify()` needed. Return a dict and Chirp serializes it as JSON.

## Error Handling

:::{tab-set}
:::{tab-item} Flask
```python
@app.errorhandler(404)
def not_found(error):
    return render_template("404.html"), 404
```
:::{/tab-item}

:::{tab-item} Chirp
```python
@app.error(404)
def not_found(request: Request):
    return Template("404.html", path=request.path)
```
:::{/tab-item}
:::{/tab-set}

Chirp's error handlers use the same return-value system. No tuple return for status codes.

## Template Filters

:::{tab-set}
:::{tab-item} Flask
```python
@app.template_filter()
def currency(value):
    return f"${value:,.2f}"
```
:::{/tab-item}

:::{tab-item} Chirp
```python
@app.template_filter()
def currency(value: float) -> str:
    return f"${value:,.2f}"
```
:::{/tab-item}
:::{/tab-set}

Identical decorator pattern. Chirp adds type annotations.

## Middleware

:::{tab-set}
:::{tab-item} Flask
```python
# Flask uses WSGI middleware or before/after_request
@app.before_request
def before():
    g.start = time.monotonic()

@app.after_request
def after(response):
    elapsed = time.monotonic() - g.start
    response.headers["X-Time"] = f"{elapsed:.3f}"
    return response
```
:::{/tab-item}

:::{tab-item} Chirp
```python
async def timing(request: Request, next: Next) -> Response:
    start = time.monotonic()
    response = await next(request)
    return response.with_header("X-Time", f"{time.monotonic() - start:.3f}")

app.add_middleware(timing)
```
:::{/tab-item}
:::{/tab-set}

Chirp uses a single middleware function instead of separate before/after hooks.

## Sessions

:::{tab-set}
:::{tab-item} Flask
```python
from flask import session

@app.route("/login", methods=["POST"])
def login():
    session["user_id"] = user.id
    return redirect("/dashboard")
```
:::{/tab-item}

:::{tab-item} Chirp
```python
from chirp import g, Redirect

@app.route("/login", methods=["POST"])
async def login(request: Request):
    form = await request.form()
    user = authenticate(form)
    g.session["user_id"] = user.id
    return Redirect("/dashboard")
```
:::{/tab-item}
:::{/tab-set}

Chirp sessions live on `g.session` (requires `SessionMiddleware`).

## What Chirp Adds

Beyond Flask equivalents, Chirp offers:

- **Fragment rendering** -- `Fragment("page.html", "block_name")` renders a named block
- **Streaming HTML** -- `Stream("page.html")` for progressive rendering
- **Server-Sent Events** -- `EventStream(generator())` for real-time updates
- **Typed contracts** -- `app.check()` validates htmx references at startup
- **Free-threading** -- Designed for Python 3.14t from day one

## Quick Reference

| Flask | Chirp |
|-------|-------|
| `Flask(__name__)` | `App()` |
| `app.config["KEY"]` | `AppConfig(key=...)` |
| `render_template()` | `Template(...)` |
| `jsonify()` | Return a dict |
| `request.args` | `request.query` |
| `request` (global) | `request` (parameter) |
| `redirect()` | `Redirect(...)` |
| `session["key"]` | `g.session["key"]` |
| `@app.errorhandler` | `@app.error` |
| `<int:id>` | `{id:int}` |
| N/A | `Fragment(...)` |
| N/A | `Stream(...)` |
| N/A | `EventStream(...)` |

## Next Steps

- [[docs/tutorials/htmx-patterns|htmx Patterns]] -- Common htmx + Chirp workflows
- [[docs/get-started/quickstart|Quickstart]] -- Build your first app
- [[docs/templates/fragments|Fragments]] -- The key differentiator
