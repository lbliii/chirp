---
title: Built-in Middleware
description: The middleware Chirp ships — CORS, static files, sessions, auth, CSRF, security headers, rate limiting, and host validation — plus the secure-by-default stack and the order to wire it.
draft: false
weight: 20
lang: en
type: doc
tags: [middleware, cors, static, sessions, auth, csrf, security, csp]
keywords: [cors, static-files, sessions, auth, csrf, html-inject, middleware, allowed-hosts, csp-nonce]
category: guide
---

## Overview

Middleware wraps every request before it reaches your handler and every response
on the way out — for cross-origin rules, static files, sessions, authentication,
CSRF, security headers, and host validation. You add each one with
`app.add_middleware(...)`, and **order matters**: sessions must come before CSRF,
and before auth.

Most apps need only a few. The one rule worth memorizing: every app with a
**mutating route** (a `POST`/`PUT`/`PATCH`/`DELETE` handler, or a page that ships
`_actions.py`) should wire the secure-by-default stack —
`SessionMiddleware` → `CSRFMiddleware` → `SecurityHeadersMiddleware`. Chirp's
`app.check()` flags a mutating route that's missing it.

This page is the catalog. Skim the index, then jump to the row you need.

:::{warning}
A mutating app missing the `SessionMiddleware` → `CSRFMiddleware` →
`SecurityHeadersMiddleware` stack is an **ERROR in production** (and a WARNING in
staging) at `app.check()`. Order is part of the contract: `SessionMiddleware`
must be registered *before* `CSRFMiddleware` and `AuthMiddleware`. See
[[docs/quality/contracts-debugging/categories|the secure-by-default contract]] for
the dev-vs-prod severity rules.
:::

### The secure-by-default stack

`chirp new` scaffolds this wiring for you. To add it by hand, register the three
in this order:

::::{steps}
:::{step} SessionMiddleware

Signed cookie sessions. CSRF and auth both depend on it, so it goes first.

```python
app.add_middleware(SessionMiddleware(SessionConfig(secret_key=SECRET_KEY)))
```

:::{/step}
:::{step} CSRFMiddleware

Validates a token on every mutating request. Requires the session to already be active.

```python
app.add_middleware(CSRFMiddleware())
```

:::{/step}
:::{step} SecurityHeadersMiddleware

Adds clickjacking, MIME-sniffing, referrer, and CSP headers to HTML responses.

```python
app.add_middleware(SecurityHeadersMiddleware())
```

:::{/step}
::::

Add `AuthMiddleware` after `SessionMiddleware` (and before your protected routes)
if the app has logins. Read `SECRET_KEY` from the environment — see
[[docs/about/core-concepts/configuration|secret_key and AppConfig]].

### Middleware at a glance

::::{list-table}
:header-rows: 1

* - Middleware
  - What it does
  - Requires
  - Import
* - [CORS](#corsmiddleware)
  - Cross-origin rules for API / htmx requests
  - —
  - `chirp.middleware`
* - [StaticFiles](#staticfiles)
  - Serve CSS / JS / images from a directory
  - —
  - `chirp.middleware`
* - [Session](#sessionmiddleware)
  - Signed cookie sessions
  - `itsdangerous`
  - `chirp.middleware.sessions`
* - [Auth](#authmiddleware)
  - Session + bearer-token authentication
  - `SessionMiddleware`
  - `chirp.middleware.auth`
* - [CSRF](#csrfmiddleware)
  - Token validation on mutating requests
  - `SessionMiddleware`
  - `chirp.middleware`
* - [SecurityHeaders](#securityheadersmiddleware)
  - Security headers on HTML responses
  - —
  - `chirp.middleware`
* - [AuthRateLimit](#authratelimitmiddleware)
  - Rate-limit login / signup / reset endpoints
  - —
  - `chirp.middleware`
* - [Audit](#auditmiddleware)
  - Opt-in per-request who/what/when/status trail (off by default)
  - —
  - `chirp.middleware`
* - [AllowedHosts](#allowedhostsmiddleware)
  - Reject spoofed `Host` headers
  - —
  - `chirp.middleware.allowed_hosts`
* - [CSPNonce](#cspnoncemiddleware)
  - Per-request nonce for inline scripts
  - —
  - `chirp.middleware.csp_nonce`
* - [HTMLInject](#htmlinject)
  - Inject a snippet before `</body>`
  - —
  - `chirp.middleware`
::::

Alpine.js and htmx scripts are injected by flags, not middleware you wire —
see [Script injection](#script-injection) at the end.

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

Handles preflight `OPTIONS` requests automatically. Supports multiple origins,
exposed headers, and credentials.

:::{warning}
Credentialed CORS requires explicit origins. `CORSConfig(allow_credentials=True)`
raises `ConfigurationError` when `allow_origins` includes `"*"` — a wildcard with
credentials is a CORS spec violation that browsers reject anyway.
:::

## StaticFiles

Serve static assets (CSS, JS, images) from a directory. Use `prefix="/static"` for
a sub-path, or `prefix="/"` to host a full static site at the root:

::::{code-tabs}

```python title="Static directory"
from chirp.middleware import StaticFiles

# Serve /static/* from the "static" directory
app.add_middleware(StaticFiles(
    directory="static",
    prefix="/static",
))
```

```python title="Full static site"
from chirp.middleware import StaticFiles

# Serve a whole site from the root with a custom 404
app.add_middleware(StaticFiles(
    directory="public",
    prefix="/",
    not_found_page="404.html",
))
```

::::

Both modes share the same hardening:

- **Path-traversal protection** — uses `is_relative_to()` to prevent directory escape
- **Index resolution** — serves `index.html` for directory paths
- **Trailing-slash redirects** — redirects `/dir` to `/dir/` when a directory exists
- **Custom 404** — pass `not_found_page` to serve a custom not-found page

## SessionMiddleware

Signed cookie sessions using `itsdangerous`:

```python
from chirp.middleware.sessions import SessionConfig, SessionMiddleware

app.add_middleware(SessionMiddleware(SessionConfig(
    secret_key="change-me-in-production",
    secure=True,  # HTTPS-only cookie; set in production
)))
```

:::{note}
Requires the `itsdangerous` package. A `ConfigurationError` is raised at startup
if it is not installed or if `secret_key` is empty.
:::

Session data is JSON-serialized into a signed cookie with sliding expiration.
Access the session dict via `get_session()`:

```python
from chirp.middleware.sessions import get_session

@app.route("/count")
def count():
    session = get_session()
    session["visits"] = session.get("visits", 0) + 1
    return f"Visits: {session['visits']}"
```

`get_session()` returns a plain `dict[str, Any]` backed by a `ContextVar` — safe
under free-threading.

::::{dropdown} All SessionConfig options
:icon: settings

| Option | Default | Description |
|--------|---------|-------------|
| `secret_key` | *(required)* | Signing key for the cookie |
| `cookie_name` | `"chirp_session"` | Cookie name |
| `max_age` | `86400` (24h) | Sliding expiration in seconds |
| `httponly` | `True` | Prevent JavaScript access |
| `samesite` | `"lax"` | SameSite policy |
| `secure` | `False` | HTTPS-only (set `True` in production) |
| `signer_digest` | `"sha256"` | Cookie HMAC digest (`"sha256"` or `"sha512"`); SHA-1 cookies from older releases still read |
| `idle_timeout_seconds` | `None` | Optional idle timeout before the session expires |
| `absolute_timeout_seconds` | `None` | Optional absolute max lifetime for a session |
::::

## AuthMiddleware

Dual-mode authentication: session cookies (browsers) and bearer tokens (API
clients). The authenticated user is stored in a `ContextVar`, accessible via
`get_user()` from any handler.

### Setup

`AuthMiddleware` requires `SessionMiddleware` for session-based auth. Register
sessions first:

```python
from chirp.middleware.sessions import SessionConfig, SessionMiddleware
from chirp.middleware.auth import AuthConfig, AuthMiddleware

app.add_middleware(SessionMiddleware(SessionConfig(secret_key="...")))
app.add_middleware(AuthMiddleware(AuthConfig(
    load_user=my_load_user,        # async (id: str) -> User | None
    verify_token=my_verify_token,  # async (token: str) -> User | None
)))
```

You must provide at least one of `load_user` (session auth) or `verify_token`
(token auth). A `ConfigurationError` is raised if neither is set.

Your user model just needs `id` and `is_authenticated` (add a `permissions`
attribute for `@requires()`):

```python
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class User:
    id: str
    name: str
    is_authenticated: bool = True
    permissions: frozenset[str] = frozenset()
```

### Login and Logout

Use the `login()` and `logout()` helpers in your handlers:

::::{code-tabs}

```python title="Login"
from chirp import login, Redirect, Template

@app.route("/login", methods=["POST"])
async def do_login(request: Request):
    form = await request.form()
    user = await verify_credentials(form["username"], form["password"])
    if user:
        login(user)
        return Redirect("/dashboard")
    return Template("login.html", error="Invalid credentials")
```

```python title="Logout"
from chirp import logout, Redirect

@app.route("/logout", methods=["POST"])
def do_logout():
    logout()
    return Redirect("/")
```

::::

:::{note}
Both `login()` and `logout()` **regenerate the session** automatically to prevent
session-fixation attacks. All previous session data is discarded — the new session
starts empty (with only the user ID set on login).
:::

### Route Protection

Use `@login_required` and `@requires()` to protect routes. Both work with sync and
async handlers:

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

For object-level authorization, pass a `policy=` callback:

```python
def owner_policy(user, request):
    return request.query.get("owner_id") == user.id

@app.route("/docs/{doc_id}")
@requires("editor", policy=owner_policy)
def edit_doc(doc_id: str):
    ...
```

Responses are content-negotiated: browser requests redirect to `login_url`, API
requests get 401/403 JSON errors.

### Safe Redirects

When `@login_required` redirects to `login_url`, it appends a URL-encoded `?next=`
parameter. To safely honour it after login, gate it through `is_safe_url()`:

```python
from chirp import is_safe_url, Redirect

@app.route("/login", methods=["POST"])
async def do_login(request: Request):
    # ... verify credentials, then login(user) ...
    next_url = request.query.get("next", "/dashboard")
    if not is_safe_url(next_url):
        next_url = "/dashboard"
    return Redirect(next_url)
```

`is_safe_url(url)` returns `True` only for relative paths on the same origin (starts
with `/`, not `//`, no scheme). This blocks open-redirect attacks where an attacker
crafts a link like `/login?next=//evil.com`.

### Templates

`AuthMiddleware` auto-registers `current_user()` as a template global:

```html
{% if current_user().is_authenticated %}
    <a href="/profile">{{ current_user().name }}</a>
{% else %}
    <a href="/login">Sign in</a>
{% endif %}
```

::::{dropdown} All AuthConfig options + password hashing
:icon: lock

**AuthConfig:**

| Option | Default | Description |
|--------|---------|-------------|
| `load_user` | `None` | `async (id: str) -> User \| None` for session auth |
| `verify_token` | `None` | `async (token: str) -> User \| None` for token auth |
| `login_url` | `"/login"` | Redirect URL for unauthenticated browsers |
| `session_key` | `"user_id"` | Session dict key for the user ID |
| `token_header` | `"Authorization"` | Header for bearer tokens |
| `token_scheme` | `"Bearer"` | Expected scheme prefix |
| `session_version` | `None` | Optional callback `user -> version` for session invalidation |
| `session_version_key` | `"_session_version"` | Session key used by `session_version` |
| `exclude_paths` | `frozenset()` | Paths that skip auth entirely |
| `token_revocation_store` | `None` | Optional `TokenRevocationStore` consulted after `verify_token` to reject revoked bearer tokens (per-`jti` + per-user `iat <= revoked_at` cutoff). Unset = no bearer revocation. Fails open on store error. |
| `token_claims` | `None` | Optional `(token) -> {jti, sub, iat}` callback (sync or async) that surfaces an opaque token's claims for the revocation store. Without it the per-user cutoff axis is skipped. |

**Password hashing** — argon2id (preferred) or scrypt (stdlib fallback):

```python
from chirp.security.passwords import hash_password, verify_password

hashed = hash_password("user-password")        # Store this
ok = verify_password("user-password", hashed)   # Check on login
```

For argon2id, install the `auth` extra: `pip install bengal-chirp[auth]`. Without
it, scrypt (always available) is used as a fallback.
::::

::::{note} See also
- [[docs/quality/deployment/auth-hardening|Hardening auth for production]]
- [[docs/examples/kanban-shell|Complete auth example (kanban_shell)]]
::::

## CSRFMiddleware

CSRF protection for form submissions. Validates a token on `POST`, `PUT`, `PATCH`,
and `DELETE` requests:

```python
from chirp.middleware import CSRFMiddleware

app.add_middleware(CSRFMiddleware())
```

Emit the token with `csrf_field()` in any form:

```html
<form method="post" action="/submit">
  {{ csrf_field() }}
  <!-- form fields -->
  <button type="submit">Submit</button>
</form>
```

Register `SessionMiddleware` *before* `CSRFMiddleware` — see
[the stack above](#the-secure-by-default-stack).

## SecurityHeadersMiddleware

Add security headers to HTML responses per HTML Living Standard recommendations:

```python
from chirp.middleware import SecurityHeadersMiddleware

app.add_middleware(SecurityHeadersMiddleware())
```

Headers are applied **only to `text/html` responses** (skipped for JSON, SSE, and
other non-HTML content types):

- **X-Frame-Options** — prevents clickjacking (default `DENY`)
- **X-Content-Type-Options** — prevents MIME sniffing (default `nosniff`)
- **Referrer-Policy** — controls referrer leakage (default `strict-origin-when-cross-origin`)
- **Content-Security-Policy** — script/style/resource policy (default: strict self-hosted baseline)
- **Strict-Transport-Security** — optional HSTS when configured

```python
from chirp.middleware.security_headers import (
    SecurityHeadersConfig,
    SecurityHeadersMiddleware,
)

app.add_middleware(SecurityHeadersMiddleware(SecurityHeadersConfig(
    x_frame_options="SAMEORIGIN",
)))
```

## AuthRateLimitMiddleware

A keyed in-memory limiter. The defaults target the common auth endpoints
(login/signup/reset) keyed by trusted client IP, but with `key_fn` plus open
path targeting it limits **any** route or group — per-user, per-resource, or
per-tenant.

```python
from chirp.middleware import AuthRateLimitConfig, AuthRateLimitMiddleware

app.add_middleware(AuthRateLimitMiddleware(AuthRateLimitConfig(
    requests=10,
    window_seconds=60,
    block_seconds=300,
    paths=("/login", "/password-reset"),
)))
```

Returns `429 Too Many Requests` with `Retry-After` when the threshold is
exceeded. By default it keys requests by `request.trusted_client_ip` — the
trusted-proxy-corrected client IP, never a raw client-supplied
`X-Forwarded-For` (which is spoofable). To key on a trusted, server-set
identity header instead (e.g. an authenticated API-key header), set
`key_header`; it is consumed verbatim, never comma-split.

### Targeting arbitrary routes with a custom key

Set `paths=()` to limit **every** matching-method route, and supply `key_fn`
to compute the bucket key per request. Return a non-empty `str` to key on it,
or `None` to **skip** rate-limiting that request (an explicit per-request
opt-out):

```python
app.add_middleware(AuthRateLimitMiddleware(AuthRateLimitConfig(
    requests=30,
    window_seconds=60,
    paths=(),  # every POST route
    # Key per authenticated user. Skip anonymous requests here (None) so the
    # default trusted-IP limiter on the auth endpoints handles them instead.
    key_fn=lambda req: f"user:{req.user.id}" if req.user.is_authenticated else None,
)))
```

:::{warning}
`key_fn` is an authorization-adjacent input. Derive the key from a
**server-side** identity — `request.user.id`, `request.trusted_client_ip`, or a
route param resolved against your records — never from a value the caller can
freely rotate (a query param, a request body field, a raw `X-Forwarded-For`),
or a client can dodge its own bucket.
:::

### HTML 429 for htmx form-action POSTs

By default the over-limit body is plain text. Set `error_template` (and
optionally `error_block`) to render an HTML `429` for htmx requests — the
middleware renders the block (or whole template, with `retry_after` in context)
to the response itself:

```python
app.add_middleware(AuthRateLimitMiddleware(AuthRateLimitConfig(
    paths=(),
    error_template="rate_limit.html",
    error_block="too_many",   # block in rate_limit.html; rendered for htmx POSTs
)))
```

Non-htmx and unconfigured over-limit responses keep the plain `Too Many
Requests` body. A configured block that does not exist is fail-loud
(`BlockNotFoundError`) — point at a block that exists.

### Pluggable backends

The in-memory backend is per-worker. For a shared limit across workers, pass a
backend implementing the `RateLimitBackend` protocol (both importable from
`chirp.middleware`). A Redis sliding-window backend ships behind the `redis`
extra:

```python
from chirp.middleware import AuthRateLimitConfig, redis_rate_limit_backend

config = AuthRateLimitConfig(
    backend=redis_rate_limit_backend("redis://localhost:6379/0"),
)
```

## AuditMiddleware

Emit a per-request who/what/when/status audit trail through the **same**
security-event sink as login/CSRF events, under an `http.request` namespace —
so audit and auth telemetry stay one pipeline:

```python
from chirp.middleware.audit import AuditConfig, AuditMiddleware

app.add_middleware(AuditMiddleware(AuditConfig(level="metadata")))
```

It is **opt-in and off by default** (`level="none"`). Verbosity is tiered:

- `"none"` — disabled (default).
- `"metadata"` — method, path, `status_code`, `source_ip`, `user_agent`,
  `user_id` only.
- `"request"` — metadata **plus** a byte-capped, redacted request-body snapshot.
- `"request_response"` — reserved; behaves like `"request"` for body capture.

Only `audited_methods` are trailed — by default the canonical
`MUTATING_METHODS` (`POST`/`PUT`/`PATCH`/`DELETE`). Events are delivered to the
sink set by `AppConfig(audit_sink=...)` (`"log"` structured-logs them) or
`set_security_event_sink(...)`. The new fields ride in `event.details`
(`status_code`, `source_ip`, `user_agent`, and at `level="request"`+ a `body`).

```python
from chirp.middleware.audit import AuditConfig, AuditMiddleware

app.add_middleware(AuditMiddleware(AuditConfig(
    level="request",
    max_body_bytes=2048,
    redact_keys=("password", "token", "secret", "csrf_token", "ssn"),
    redact_patterns=(r"\d{16}",),  # mask anything that looks like a card number
)))
```

:::{important}
**Source IP is trusted, not spoofable.** `source_ip` comes from
`request.trusted_client_ip` (the trusted-proxy-corrected client) — never a
re-parsed `X-Forwarded-For`, which is client-controlled.

**Hypermedia-safe by construction.** For `Stream`, `Suspense`, and `EventStream`
return types (which resolve to `StreamingResponse` / `SSEResponse` /
`FileResponse`) the middleware downgrades to metadata-only and **never** drains
the request body — draining a stream would buffer unbounded or break it.

**`user_id` needs `AuthMiddleware`.** Without it the trail records an anonymous
user (it never crashes).
:::

Wire it as the outermost leg of the secure-by-default stack:

```python
from chirp.middleware.audit import AuditConfig
from chirp.middleware.stack import secure_stack

for mw in secure_stack(app.config, audit=AuditConfig(level="metadata")):
    app.add_middleware(mw)
```

`AuditMiddleware` is appended **after** `SecurityHeadersMiddleware` so it wraps
the whole chain and observes the final status code (including a CSRF
rejection's 403).

## AllowedHostsMiddleware

Validate the `Host` header against a whitelist, rejecting requests with spoofed or
unrecognized hosts:

```python
from chirp.middleware.allowed_hosts import AllowedHostsMiddleware

app.add_middleware(AllowedHostsMiddleware(
    ("example.com", ".example.com"),
))
```

- `"*"` — allow all hosts (default; development only)
- `".example.com"` — matches `example.com` and any subdomain (e.g. `api.example.com`)

Returns `400 Bad Request` for unrecognized hosts. Pass `debug=True` to include the
rejected host and allowed list in the error response (development only).

:::{warning}
Always set explicit allowed hosts in production. The `"*"` default is for local
development only.
:::

## CSPNonceMiddleware

Generate a per-request cryptographic nonce for `Content-Security-Policy`, allowing
inline scripts without `'unsafe-inline'`:

```python
from chirp.middleware.csp_nonce import CSPNonceMiddleware

app.add_middleware(CSPNonceMiddleware())
```

Emit the nonce in templates via `csp_nonce()`:

```html
<script nonce="{{ csp_nonce() }}">
    // Inline script allowed by CSP
</script>
```

::::{dropdown} Custom base CSP + handler access
:icon: code

Customize the base CSP directive — the middleware appends
`script-src 'self' 'nonce-<value>'` to whatever base you provide:

```python
app.add_middleware(CSPNonceMiddleware(
    base_csp="default-src 'self'; img-src 'self' https://cdn.example.com"
))
```

Read the nonce in a handler with `get_csp_nonce()`:

```python
from chirp.middleware.csp_nonce import get_csp_nonce

@app.route("/page")
def page():
    nonce = get_csp_nonce()
    return Template("page.html", nonce=nonce)
```
::::

## HTMLInject

Inject a snippet into every HTML response before `</body>`:

```python
from chirp.middleware import HTMLInject

# Inject a live-reload script in development
app.add_middleware(HTMLInject(
    '<script src="/_dev/reload.js"></script>'
))
```

Useful for development tools, analytics scripts, or debug toolbars. `HTMLInject`
does not run on streaming bodies.

## Script injection

Alpine.js and htmx scripts are injected by **config flags**, not by middleware you
wire yourself. Set one flag and Chirp owns the script tag (CDN URL, CSP nonce, and
deduplication) for you.

- **Alpine.js** — set `AppConfig(alpine=True)` (also enabled by `use_chirp_ui(app)`).
  Chirp injects the Alpine CDN bundle before `</body>` on buffered and streaming
  HTML, and registers the `alpine_json_config` template global. Details:
  [[docs/build-apps/ui-extensions/alpine|Alpine.js injection]].
- **htmx** — set `AppConfig(htmx=True)`. **Opt-in, default off.** Chirp injects the
  exact managed htmx bundle (explicit jsDelivr `/dist` paths, per-request CSP
  nonce), dedups the complete bundle on `data-chirp="htmx"`, and mirrors the
  Alpine injector. The default `2.0.10` bundle is core-only. Exact pin
  `4.0.0-beta5` selects the provisional core → `htmx-2-compat` → `hx-sse`
  preview; other htmx 4 pins fail during freeze.
  `use_chirp_ui(app)` does not auto-enable it because the chirp-ui layouts already
  ship their own htmx tag.

::::{dropdown} Injection-pipeline internals
:icon: settings

When `AppConfig(alpine=True)`, Chirp registers `AlpineInject`, which injects the
Alpine.js CDN bundle and its inline helper block before the first `</body>` on
**buffered** full-page HTML and on **`StreamingResponse`** HTML streams (for
example `Suspense`). It skips injection when the response already contains
`data-chirp="alpine"` before `</body>`, and respects fragment / render-intent
gating for non-streaming bodies. When `use_chirp_ui(app)` is active, a separate
full-page injector also adds `chirpui-alpine.js` for named chirp-ui controllers,
including on streaming HTML.

The htmx injector mirrors `AlpineInject` exactly: buffered + `StreamingResponse`
HTML, explicit jsDelivr `/dist` paths, one live per-request CSP nonce across the
bundle, `data-chirp="htmx"` whole-bundle dedup, and the same render-intent gating.
See [[docs/build-apps/ui-extensions/htmx4-preview|htmx 4 preview provisioning]]
for self-host markers and rollback.

`HTMLInject` does not run on streaming bodies; Alpine and htmx streaming are handled
only by their dedicated injectors.
::::

::::{note} See also
- [[docs/build-apps/request-pipeline/custom|Write your own middleware]]
- [[docs/build-apps/request-pipeline/_index|How the middleware pipeline orders requests]]
- [[docs/about/core-concepts/configuration|secret_key and AppConfig]]
::::

:::{related}
:::
