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
from chirp.middleware.sessions import SessionConfig, SessionMiddleware

app.add_middleware(SessionMiddleware(SessionConfig(
    secret_key="change-me-in-production",
)))
```

:::{note}
Requires the `itsdangerous` package. A `ConfigurationError` is raised at startup if it's not installed or if `secret_key` is empty.
:::

Session data is JSON-serialized into a signed cookie with sliding expiration. Access the session dict via `get_session()`:

```python
from chirp.middleware.sessions import get_session

@app.route("/count")
def count():
    session = get_session()
    session["visits"] = session.get("visits", 0) + 1
    return f"Visits: {session['visits']}"
```

`get_session()` returns a plain `dict[str, Any]` backed by a `ContextVar` -- safe under free-threading.

**Configuration options:**

| Option | Default | Description |
|--------|---------|-------------|
| `secret_key` | *(required)* | Signing key for the cookie |
| `cookie_name` | `"chirp_session"` | Cookie name |
| `max_age` | `86400` (24h) | Sliding expiration in seconds |
| `httponly` | `True` | Prevent JavaScript access |
| `samesite` | `"lax"` | SameSite policy |
| `secure` | `False` | HTTPS-only (set `True` in production) |

## AuthMiddleware

Dual-mode authentication: session cookies (browsers) and bearer tokens (API clients). The authenticated user is stored in a `ContextVar`, accessible via `get_user()` from any handler.

### Setup

`AuthMiddleware` requires `SessionMiddleware` for session-based auth. Register sessions first:

```python
from chirp.middleware.sessions import SessionConfig, SessionMiddleware
from chirp.middleware.auth import AuthConfig, AuthMiddleware

app.add_middleware(SessionMiddleware(SessionConfig(secret_key="...")))
app.add_middleware(AuthMiddleware(AuthConfig(
    load_user=my_load_user,       # async (id: str) -> User | None
    verify_token=my_verify_token,  # async (token: str) -> User | None
)))
```

You must provide at least one of `load_user` (session auth) or `verify_token` (token auth). A `ConfigurationError` is raised if neither is set.

### User Protocol

Your user model just needs `id` and `is_authenticated`:

```python
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class User:
    id: str
    name: str
    is_authenticated: bool = True
```

For `@requires()`, add a `permissions` attribute:

```python
@dataclass(frozen=True, slots=True)
class User:
    id: str
    name: str
    is_authenticated: bool = True
    permissions: frozenset[str] = frozenset()
```

### Login and Logout

Use the `login()` and `logout()` helpers in your handlers:

```python
from chirp import login, logout, Redirect

@app.route("/login", methods=["POST"])
async def do_login(request: Request):
    form = await request.form()
    user = await verify_credentials(form["username"], form["password"])
    if user:
        login(user)
        return Redirect("/dashboard")
    return Template("login.html", error="Invalid credentials")

@app.route("/logout", methods=["POST"])
def do_logout():
    logout()
    return Redirect("/")
```

### Route Protection

Use `@login_required` and `@requires()` to protect routes. Both work with sync and async handlers:

```python
from chirp import login_required, requires, get_user

@app.route("/dashboard")
@login_required
def dashboard():
    user = get_user()
    return Template("dashboard.html", user=user)

@app.route("/admin")
@requires("admin")
def admin_panel():
    return Template("admin.html")
```

Content-negotiated responses: browser requests redirect to `login_url`, API requests get 401/403 JSON errors.

### Templates

`AuthMiddleware` auto-registers `current_user()` as a template global:

```html
{% if current_user().is_authenticated %}
    <a href="/profile">{{ current_user().name }}</a>
{% else %}
    <a href="/login">Sign in</a>
{% endif %}
```

### Password Hashing

Hash and verify passwords with argon2id (preferred) or scrypt (stdlib fallback):

```python
from chirp.security.passwords import hash_password, verify_password

hashed = hash_password("user-password")      # Store this
ok = verify_password("user-password", hashed) # Check on login
```

:::{note}
For argon2id, install the `auth` extra: `pip install bengal-chirp[auth]`. Without it, scrypt (always available) is used as a fallback.
:::

### Configuration

| Option | Default | Description |
|--------|---------|-------------|
| `load_user` | `None` | `async (id: str) -> User \| None` for session auth |
| `verify_token` | `None` | `async (token: str) -> User \| None` for token auth |
| `login_url` | `"/login"` | Redirect URL for unauthenticated browsers |
| `session_key` | `"user_id"` | Session dict key for the user ID |
| `token_header` | `"Authorization"` | Header for bearer tokens |
| `token_scheme` | `"Bearer"` | Expected scheme prefix |
| `exclude_paths` | `frozenset()` | Paths that skip auth entirely |

:::{tip}
See the [`auth` example](https://github.com/your-org/chirp/tree/main/examples/auth) for a complete working app with login, logout, and protected routes.
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
