---
title: Built-in Middleware
description: CORS, StaticFiles, Sessions, Auth, CSRF, and HTMLInject
draft: false
weight: 20
lang: en
type: doc
tags: [middleware, cors, static, sessions, auth, csrf]
keywords: [cors, static-files, sessions, auth, csrf, html-inject, middleware]
category: guide
---

## CORSMiddleware

Cross-Origin Resource Sharing for API and htmx requests:

```python
from chirp.middleware import CORSMiddleware, CORSConfig

cors = CORSMiddleware(CORSConfig(
    allow_origins=["https://example.com"],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["HX-Request", "HX-Target"],
    allow_credentials=True,
    max_age=3600,
))

app.add_middleware(cors)
```

Handles preflight `OPTIONS` requests automatically. Supports multiple origins, exposed headers, and credentials.

## StaticFiles

Serve static assets (CSS, JS, images) from a directory:

```python
from chirp.middleware import StaticFiles

app.add_middleware(StaticFiles(
    directory="static",
    prefix="/static",
))
```

Features:

- **Path traversal protection** -- uses `is_relative_to()` to prevent directory escape
- **Index resolution** -- serves `index.html` for directory paths
- **Trailing-slash redirects** -- redirects `/dir` to `/dir/` when a directory exists
- **Custom 404** -- optionally serve a custom 404 page
- **Root prefix** -- use `prefix="/"` for static site hosting

```python
# Serve a full static site from the "public" directory
app.add_middleware(StaticFiles(
    directory="public",
    prefix="/",
    fallback="404.html",
))
```

## SessionMiddleware

Signed cookie sessions using itsdangerous:

```python
from chirp.middleware import SessionMiddleware

app.add_middleware(SessionMiddleware())
```

:::{note}
Requires the `sessions` extra: `pip install bengal-chirp[sessions]`. Also requires `AppConfig(secret_key="...")` to be set. A `ConfigurationError` is raised at startup if either is missing.
:::

Session data is JSON-serialized into a signed cookie with sliding expiration:

```python
from chirp import g

@app.route("/login", methods=["POST"])
async def login(request: Request):
    user = authenticate(await request.form())
    g.session["user_id"] = user.id
    return Redirect("/dashboard")

@app.route("/dashboard")
def dashboard():
    user_id = g.session.get("user_id")
    if not user_id:
        return Redirect("/login")
    return Template("dashboard.html", user=get_user(user_id))
```

## Auth Middleware

Token and session-based authentication:

```python
from chirp.middleware import AuthMiddleware

app.add_middleware(AuthMiddleware(
    login_url="/login",
    exclude_paths=["/", "/login", "/static"],
))
```

Works with the security decorators:

```python
from chirp import login_required, requires

@app.route("/profile")
@login_required
def profile():
    return Template("profile.html")

@app.route("/admin")
@requires("admin")
def admin_panel():
    return Template("admin.html")
```

:::{note}
Requires the `auth` extra for password hashing: `pip install bengal-chirp[auth]`.
:::

## CSRFMiddleware

CSRF protection for form submissions:

```python
from chirp.middleware import CSRFMiddleware

app.add_middleware(CSRFMiddleware())
```

Validates a CSRF token on `POST`, `PUT`, `PATCH`, and `DELETE` requests. The token is available in templates:

```html
<form method="post" action="/submit">
  <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
  <!-- form fields -->
  <button type="submit">Submit</button>
</form>
```

:::{note}
Requires `AppConfig(secret_key="...")` to be set.
:::

## HTMLInject

Inject a snippet into every HTML response before `</body>`:

```python
from chirp.middleware import HTMLInject

# Inject live-reload script in development
app.add_middleware(HTMLInject(
    '<script src="/_dev/reload.js"></script>'
))
```

Useful for development tools, analytics scripts, or debug toolbars.

## Next Steps

- [[docs/middleware/custom|Custom Middleware]] -- Write your own
- [[docs/middleware/overview|Overview]] -- How the middleware pipeline works
- [[docs/core-concepts/configuration|Configuration]] -- AppConfig and secret_key
