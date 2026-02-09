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

## Sessions and Auth

:::{tab-set}
:::{tab-item} Flask
```python
from flask import session, redirect
from flask_login import login_user, login_required

@app.route("/login", methods=["POST"])
def do_login():
    session["user_id"] = user.id
    login_user(user)
    return redirect("/dashboard")

@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html")
```
:::{/tab-item}

:::{tab-item} Chirp
```python
from chirp import login, logout, login_required, get_user, is_safe_url, Redirect, Template

@app.route("/login", methods=["POST"])
async def do_login(request: Request):
    form = await request.form()
    user = await verify_credentials(form["username"], form["password"])
    if user:
        login(user)  # regenerates session automatically
        next_url = request.query.get("next", "/dashboard")
        if not is_safe_url(next_url):
            next_url = "/dashboard"
        return Redirect(next_url)
    return Template("login.html", error="Invalid credentials")

@app.route("/dashboard")
@login_required
def dashboard():
    user = get_user()
    return Template("dashboard.html", user=user)
```
:::{/tab-item}
:::{/tab-set}

Chirp has built-in `login()` / `logout()` helpers and `@login_required` — no Flask-Login equivalent needed. Both `login()` and `logout()` regenerate the session to prevent session fixation attacks. Use `is_safe_url()` to validate `?next=` redirects (prevents open redirects). Requires `SessionMiddleware` + `AuthMiddleware`. See [[docs/middleware/builtin|Built-in Middleware]] for setup.

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
| `session["key"]` | `get_session()["key"]` |
| `login_user(user)` | `login(user)` (regenerates session) |
| `@login_required` | `@login_required` |
| N/A | `is_safe_url(url)` |
| `@app.errorhandler` | `@app.error` |
| `<int:id>` | `{id:int}` |
| N/A | `Fragment(...)` |
| N/A | `Stream(...)` |
| N/A | `EventStream(...)` |

## Next Steps

- [[docs/tutorials/htmx-patterns|htmx Patterns]] -- Common htmx + Chirp workflows
- [[docs/get-started/quickstart|Quickstart]] -- Build your first app
- [[docs/templates/fragments|Fragments]] -- The key differentiator
