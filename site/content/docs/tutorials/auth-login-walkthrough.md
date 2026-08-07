---
title: A Login That Is Correct by Default
description: The whole login → gated page → logout loop in one file, with secure-by-default sessions, CSRF, and password hashing — and app.check() catching the one wire you forgot
draft: false
weight: 8
lang: en
type: doc
tags: [tutorial, auth, login, sessions, csrf, security, app-check]
keywords: [chirp auth, login walkthrough, session login, csrf, secure_stack, login_required, verify_login, app.check]
category: tutorial
---

## Overview

In JS-land, "add login" means you assemble it yourself: a session store, CSRF
tokens wired through every form, cookie flags you have to remember (`Secure`,
`HttpOnly`, `SameSite`), a password hash you hope is the right algorithm, and
redirect logic for the unauthenticated case. Miss one and nothing tells you —
the cookie ships without `Secure` over HTTPS, the enumeration timing leak is
invisible, the gate 500s only when a real user hits it. Chirp's promise is the
opposite: the secure stack is in the box, the defaults are already correct
(`Secure` cookies in production, session regeneration on login, an
enumeration-safe verify), and [[docs/quality/contracts-debugging/categories|`app.check()`]]
catches the wiring mistakes **at startup** — before a user finds them for you.

This walkthrough is the whole loop — **login → gated page → logout** — in one
copy-pasteable file. Every step has a one-line *why this is safe* so you can see
what the framework is doing for you. Then we prove it: the real `app.check()`
output for the correct app, and the real error you get when you forget the one
wire that matters.

**Prerequisites:** Python 3.14+, `pip install bengal-chirp`, and
`pip install "bengal-chirp[auth]"` for argon2id password hashing (scrypt is the
stdlib fallback). Set a secret key: `export CHIRP_SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")`.

## The golden path

::::{steps}

:::{step} Bring your own user, hash the password once

Chirp does not own your user model. Any object with `id` and `is_authenticated`
satisfies the [[docs/build-apps/request-pipeline/builtin|user protocol]] — a
dataclass, an ORM row, whatever you already have. The one rule: **never store
plaintext**. Hash at write time with `hash_password`, and store the PHC string.

```python
import os
from dataclasses import dataclass
from pathlib import Path

from chirp import (
    App,
    AppConfig,
    AuthConfig,
    FormAction,
    Request,
    Template,
    ValidationError,
    current_user,
    login,
    login_required,
    logout,
    secure_stack,
)
from chirp.security import hash_password, verify_login

TEMPLATES_DIR = Path(__file__).parent / "templates"


@dataclass(frozen=True, slots=True)
class User:
    """Any object with `id` + `is_authenticated` satisfies chirp's User protocol."""

    id: str
    name: str
    password_hash: str
    is_authenticated: bool = True


# Password is hashed once at startup — never store plaintext.
USERS: dict[str, User] = {
    "ada": User(id="ada", name="Ada Lovelace", password_hash=hash_password("correct horse")),
}


async def load_user(user_id: str) -> User | None:
    """AuthMiddleware calls this each request to rehydrate the session user."""
    return USERS.get(user_id)
```

:::{tip} Why this is safe
`hash_password` uses **argon2id** (RFC 9106 cost factors) when `chirp[auth]` is
installed and falls back to stdlib scrypt otherwise — both PHC-format, both
auto-detected by `verify_password` later, so a hash survives an algorithm change.
:::
:::{/step}

:::{step} Wire the secure-by-default stack

`secure_stack(app.config)` returns the canonical
`[SessionMiddleware, CSRFMiddleware, SecurityHeadersMiddleware]` list — already
in contract-passing order. Pass `auth=AuthConfig(...)` and `AuthMiddleware` is
placed for you — right after sessions (it reads the session) and before CSRF —
so the whole stack is one loop.

```python
config = AppConfig(
    template_dir=TEMPLATES_DIR,
    secret_key=os.environ.get("CHIRP_SECRET_KEY", "dev-only-not-for-production"),
)
app = App(config=config)

# secure_stack wires the whole stack in the correct order:
# SessionMiddleware -> AuthMiddleware -> CSRFMiddleware -> SecurityHeadersMiddleware.
for mw in secure_stack(app.config, auth=AuthConfig(load_user=load_user)):
    app.add_middleware(mw)
```

:::{tip} Why this is safe
The stack is in the order the `security_stack` / `csrf_session` contracts
require, and the session cookie's `Secure` flag is `"auto"` — resolved from
`AppConfig.env`, so it is `True` in staging/production and `False` in local dev.
No manual ordering, and no debug-coupled cookie footgun.
:::
:::{/step}

:::{step} The login route — verify, then log in

`GET /login` renders the form. `POST /login` looks up the user, verifies with
`verify_login`, and on success calls `login(user)` and returns a `FormAction`. A
bad guess re-renders the form at **422** with a `ValidationError`.

```python
@app.route("/login")
def login_form():
    """Render the login form (csrf_field() injects the hidden token)."""
    return Template("login.html")


@app.route("/login", methods=["POST"])
async def do_login(request: Request):
    form = await request.form()
    username = form.get("username", "")
    password = form.get("password", "")

    user = USERS.get(username)
    # verify_login runs a decoy hash for an unknown user so the
    # "no such user" and "wrong password" paths take comparable time.
    if not verify_login(password, user.password_hash if user else None):
        return ValidationError(
            "login.html",
            "form",
            error="Invalid username or password.",
            username=username,
        )

    login(user)  # regenerates the session (fixation defence) + sets the user id
    # htmx gets HX-Redirect; a plain POST gets a 303 to /dashboard.
    return FormAction("/dashboard")
```

:::{tip} Why this is safe
**`verify_login`** kills the user-enumeration timing oracle: for an unknown user
it passes `None` and still runs a full decoy-hash verify before returning
`False`, so "no such user" and "wrong password" take comparable time. Always
call it — don't short-circuit on `user is None`, or the decoy never runs.

**`login(user)`** regenerates the session *before* binding the user id, so the
pre-auth session is discarded — that is the session-fixation defence (you can
see it in the proof below: a fresh session cookie after correct login).
:::
:::{/step}

:::{step} The gated page and logout

`@login_required` gates `/dashboard`. An anonymous browser is content-negotiated
to a **302 → `/login?next=/dashboard`**. `logout()` regenerates the session,
clearing all auth state.

```python
@app.route("/dashboard")
@login_required
def dashboard():
    """Gated: anonymous browsers are 302'd to /login?next=/dashboard."""
    return Template("dashboard.html", user=current_user())


@app.route("/logout", methods=["POST"])
def do_logout():
    logout()  # regenerates the session, clearing all auth state
    return FormAction("/login")


if __name__ == "__main__":
    app.run()
```

:::{tip} Why this is safe
**`@login_required`** redirects unauthenticated browsers to `login_url` with
`?next=` preserved — *and* stamps a static marker that the `auth_middleware`
contract check reads to prove the route is gated **without executing it**. That
marker is what makes the safety net in the next section possible.
:::
:::{/step}

::::{/steps}

### The templates

Three small Kida templates. The only security-critical line is `{{ csrf_field() }}`
inside each `<form>` — it emits the hidden `_csrf_token` input bound to the
session, which `CSRFMiddleware` validates on every POST.

```html
{# templates/base.html #}
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{% block title %}Auth{% endblock %}</title>
</head>
<body>
  <main>
    {% block content %}{% endblock %}
  </main>
</body>
</html>
```

```html
{# templates/login.html #}
{% extends "base.html" %}
{% block title %}Sign in{% endblock %}
{% block content %}
<h1>Sign in</h1>
{% block form %}
<form id="form" method="post" action="/login">
  {{ csrf_field() }}
  {% if error is defined %}<p role="alert">{{ error }}</p>{% endif %}
  <label for="username">Username</label>
  <input id="username" name="username" value="{{ username | default('') }}" required>
  <label for="password">Password</label>
  <input id="password" name="password" type="password" required>
  <button type="submit">Sign in</button>
</form>
{% endblock %}
{% endblock %}
```

```html
{# templates/dashboard.html #}
{% extends "base.html" %}
{% block title %}Dashboard{% endblock %}
{% block content %}
<h1>Welcome, {{ user.name }}</h1>
<p>You are signed in as <code>{{ user.id }}</code>.</p>
<form method="post" action="/logout">
  {{ csrf_field() }}
  <button type="submit">Sign out</button>
</form>
{% endblock %}
```

:::{tip} Why this is safe
`csrf_field()` binds the token to the *current* session. Because `login()` and
`logout()` regenerate the session, the token rotates on every auth transition —
the page re-render hands the fresh token to htmx automatically. A POST that
reuses a stale token gets a **403**, so no state-changing request succeeds
without a same-session token.
:::

Run it:

```bash
CHIRP_SECRET_KEY=... python app.py
```

## Prove it

Two ways to know this works: the loop behaves (exercised below), and — the part
that makes it lovable — `app.check()` verifies the whole posture at startup.

### The loop, end to end

Driven with [[docs/quality/testing/_index|`TestClient`]] (carrying the session
cookie and scraping the CSRF token from each form), the observed flow:

```text
anon GET /dashboard       → 302  Location='/login?next=%2Fdashboard'
GET /login                → 200  csrf_field present; session cookie issued
POST /login (wrong)       → 422  shows the error; user stays anonymous
  then GET /dashboard     → 302  still gated
POST /login (correct)     → 303  HX-Redirect='/dashboard'; FRESH session cookie set
authed GET /dashboard     → 200  renders the user name
POST /logout              → 303  HX-Redirect='/login'
  then GET /dashboard     → 302  session cleared, gated again
```

The fresh session cookie after correct login is the session-fixation defence
made visible: `login()` discarded the pre-auth session. Wrong creds 422 and the
user stays anonymous. Logout clears the session, and `/dashboard` 302s again.

### `app.check()` on the correct app

A satisfied security check emits **nothing** — no `security_stack`,
`csrf_session`, `cookie_secure`, or `auth_middleware` finding. That silence *is*
the pass signal. Here is the real output:

```text
  ── chirp check ──────────────────────────────────────────────────

  4 routes · 239 templates · 2 targets · 99.4ms elapsed

  Routing

  ·  Route '/dashboard' is not referenced from any template.
     route /dashboard

  HTMX

  ▲  Mutating htmx request has no explicit hx-target and may inherit a broad container target. This can replace large UI regions with partial responses. Consider Action() (204), hx-swap="none", or an explicit local hx-target.
     in login.html
     Inherited broad target(s): #main (chirp/layouts/boost.html), #main (chirpui/app_layout.html)

  ▲  Mutating htmx request has no explicit hx-target and may inherit a broad container target. This can replace large UI regions with partial responses. Consider Action() (204), hx-swap="none", or an explicit local hx-target.
     in dashboard.html
     Inherited broad target(s): #main (chirp/layouts/boost.html), #main (chirpui/app_layout.html)

  Forms

  ·  <form action="/login" method="post"> targets route '/login' which accepts POST but has no FormContract. Consider adding @contract(form=FormContract(...)) for validation and type safety.
     in login.html
     route /login

  ·  <form action="/logout" method="post"> targets route '/logout' which accepts POST but has no FormContract. Consider adding @contract(form=FormContract(...)) for validation and type safety.
     in dashboard.html
     route /logout

  ✓  No errors · 2 warnings

  ─────────────────────────────────────────────────────────────────
```

Exit code `0`. None of these findings are security-related: an INFO orphan-route
note, two WARNING htmx broad-target advisories that originate from Chirp's
**built-in** layout templates picked up in the template scan, and two INFO
form-contract upsells. A production app can silence them with explicit
`hx-target` and `@contract(form=...)`; the auth posture is already clean.

### Forget the one wire that matters

Now remove `AuthMiddleware` from the stack and keep the gated `@login_required`
`/dashboard`. Run the production-posture preflight (`app.check(deploy=True)`, or
`chirp check --deploy`). Chirp catches it at startup:

```text
  ✗  Route '/dashboard' declares auth (RouteMeta.auth or @login_required/@requires) but AuthMiddleware is not registered while env='production'. The auth gate calls get_user(), which raises LookupError -> a 500 at request time without AuthMiddleware. Register AuthMiddleware after SessionMiddleware in the stack.
     route /dashboard
```

This is the safety net. Without it, the missing middleware surfaces as a 500 the
first time a user hits the gate. With it, you find out at startup — the framework
read the static `@login_required` marker, saw no `AuthMiddleware`, and told you
exactly what to add and where. **The framework is the expert; you do not have to
remember the wire.**

:::{note}
The `auth_middleware` check is **env-aware**: it is an ERROR under
production/staging posture and silent in development (where the request-time 500
surfaces it locally anyway). That is why the broken-app demo uses
`app.check(deploy=True)` — wire `chirp check --deploy` as your CI gate to catch
it. This matches the rest of the [[docs/quality/contracts-debugging/categories|env-aware severity model]].
:::

:::{tip}
Running `chirp check --deploy` on the *correct* app surfaces a few **non-auth**
production-hardening items too — a wildcard `allowed_hosts`, a CSP without a
nonce, and an HSTS reminder. Those are about general production posture, not this
login flow (the auth posture above is clean); see
[[docs/quality/deployment/production|deploying to production]] for the rest.
:::

## Going further

The golden path is correct by default. Here is where each piece extends:

- **Rehash on login** — `verify_and_upgrade(password, hash)` verifies *and*
  returns a freshly computed hash when the stored one is stale (parameter
  upgrades by default; pass `upgrade_algorithm=True` for scrypt→argon2 during a
  migration window). Persist the returned hash; never rehashes a wrong guess.
  See [[docs/quality/deployment/auth-hardening|Auth Hardening]].
- **Declarative gating** — instead of the `@login_required` decorator, set
  `RouteMeta.auth` (or an `AuthSpec`) on a mounted filesystem page; the same
  `auth_middleware` / `auth_spec` checks enforce it. See
  [[docs/build-apps/pages-navigation/route-directory|the route directory]].
- **Ergonomic accessors** — `request.user` (never raises → `AnonymousUser`) and
  `request.session` (raises without `SessionMiddleware`, by design) are
  properties on `Request`; `current_user()` and `session()` are the template
  globals.
- **Production posture** — `chirp check --deploy` re-runs the env-aware rules
  with `env="production"` against a throwaway config view, so you find every
  production-only failure before you ship. See [[docs/quality/deployment/production|Production Deployment]].
- **Passkeys** — WebAuthn / passkey support ships in `chirp.security.passkeys`
  (opt-in via `pip install chirp[passkeys]` and `AppConfig(passkeys=True)`). The
  framework owns the ceremony verbs and session-bound challenge lifecycle; your
  app owns the credential row — same BYO doctrine as the `User` protocol. See
  [[docs/tutorials/passkeys-walkthrough|Passkeys walkthrough]] and
  `examples/standalone/passkeys_minimal/`.

:::{note} See also
- [[docs/quality/deployment/auth-hardening|Auth Hardening]] — the full production wiring checklist
- [[docs/quality/contracts-debugging/categories|Contract categories]] — the env-aware severity model these checks use
- [[docs/build-apps/request-pipeline/builtin|Built-in Middleware]] — Session, Auth, CSRF, and SecurityHeaders in depth
- [[docs/tutorials/coming-from-flask|Coming from Flask]] — the same login mapped from Flask-Login
:::
