---
title: Auth Hardening
description: The wiring checklist for exposing an app with logins or user data to the internet
draft: false
weight: 20
lang: en
type: doc
tags: [auth, security, hardening]
keywords: [auth hardening, csrf, sessions, csp, hsts, rate limit]
category: guide
---

## Overview

This is the checklist you run before exposing an app with logins or user data to
the internet. Chirp ships the secure-by-default building blocks — sessions, CSRF,
rate limiting, security headers, password hashing — but you wire and configure
them for production yourself. This page is that wiring.

:::{note}
Most of these items are also enforced by `app.check()`, the contracts you run in
CI. The severity is environment-aware: missing CSRF or session protection on a
mutating route is an **ERROR in production**, a **WARNING in staging**, and
**silent in development**. This checklist and the contract categories cover the
same ground from two angles — see [[docs/quality/contracts-debugging/categories|the contract categories]].
:::

## Minimal hardened setup

Copy this stack, then read the per-item rationale below. The registration order
matters: `SessionMiddleware` runs first so a session exists, then
`AuthRateLimitMiddleware` and `CSRFMiddleware` (which depends on the session),
then `SecurityHeadersMiddleware`.

```python
import os

from chirp.middleware.auth_rate_limit import AuthRateLimitConfig, AuthRateLimitMiddleware
from chirp.middleware.csrf import CSRFMiddleware
from chirp.middleware.security_headers import (
    SecurityHeadersConfig,
    SecurityHeadersMiddleware,
)
from chirp.middleware.sessions import SessionConfig, SessionMiddleware

secret = os.environ["CHIRP_SECRET_KEY"]

app.add_middleware(
    SessionMiddleware(
        SessionConfig(
            secret_key=secret,
            secure=True,
            httponly=True,
            samesite="lax",
            idle_timeout_seconds=1800,
            absolute_timeout_seconds=86400,
        )
    )
)
app.add_middleware(
    AuthRateLimitMiddleware(AuthRateLimitConfig(paths=("/login", "/password-reset")))
)
app.add_middleware(CSRFMiddleware())
app.add_middleware(
    SecurityHeadersMiddleware(
        SecurityHeadersConfig(
            content_security_policy="default-src 'self'; frame-ancestors 'none'; object-src 'none'",
            strict_transport_security="max-age=63072000; includeSubDomains",
        )
    )
)
```

:::{warning}
`AuthRateLimitMiddleware` keys its rate-limit buckets off the socket client
address by default. Behind a trusted proxy that rewrites forwarded headers, every
request arrives from the proxy IP — so all clients share one bucket and the limit
is meaningless. Pass `key_header="x-forwarded-for"` so the middleware reads the
real client address from the proxy chain. Only set this when you control the proxy
and it strips inbound `X-Forwarded-For`, or an attacker can spoof the header.
:::

## What each item does

Each row maps a hardening area to the field you set in the stack above.

:::{list-table}
:header-rows: 1

* - Area
  - What to set
  - Symbol / value
* - Session cookies
  - Sign cookies (HMAC-SHA-256 by default), mark them secure and HTTP-only, and bound their lifetime. `secure` defaults to `"auto"` (Secure in production/staging via `AppConfig.env`, off in local dev); the explicit `secure=True` below is belt-and-suspenders.
  - `SessionConfig(secure=True, httponly=True, samesite="lax", signer_digest="sha256", idle_timeout_seconds=..., absolute_timeout_seconds=...)`
* - Session invalidation
  - Invalidate stale sessions after a password change or account event
  - `AuthConfig(session_version=...)`
* - CSRF
  - Validate unsafe requests; emit a token in every mutating form
  - `CSRFMiddleware()` + `{{ csrf_field() }}`
* - Authorization
  - Gate routes; add an ownership check; return 403 without leaking policy detail
  - `@login_required`, `@requires("role", policy=...)`
* - Abuse protection
  - Rate-limit auth endpoints; add lockout/backoff on repeated failures
  - `AuthRateLimitMiddleware(...)`, `LoginLockout(...)`
* - Browser headers
  - Strict Content-Security-Policy; HSTS over HTTPS; keep the safe defaults
  - `SecurityHeadersConfig(content_security_policy=..., strict_transport_security=...)`
* - Password hashing
  - Use argon2 in production
  - `pip install bengal-chirp[auth]`
* - Audit
  - Register a sink and alert on auth/CSRF/authz event spikes
  - `set_security_event_sink(...)`
:::

The authorization decorators and lockout helpers live in `chirp.security`, not
`chirp.middleware`:

```python
from chirp.security import LockoutConfig, LoginLockout, login_required, requires
```

`policy=` is a keyword parameter of `@requires(...)`, not a separate API. It takes
a callback that receives the user and request and returns a bool for object-level
ownership checks.

### Audit events to alert on

Register a sink with `set_security_event_sink(...)`, then alert on spikes in these
event names:

:::{list-table}
:header-rows: 1

* - Event
  - Fires when
* - `auth.token.invalid`
  - A bearer token fails verification
* - `csrf.reject.missing` / `csrf.reject.invalid`
  - A mutating request has no CSRF token or a bad one
* - `authz.permission.denied`
  - A `@requires(role)` check fails
* - `authz.policy.denied`
  - A `@requires(..., policy=...)` ownership check fails
:::

## Account-recovery flows

Chirp does not ship password-reset or email-verification flows. If you are
wondering where they are, expand the boundary statement below.

:::{dropdown} Why Chirp has no built-in password-reset or email flow
Chirp ships session auth, CSRF, rate limiting, and password hashing — but it does
not own account-recovery flows like password reset or email verification. This is
a deliberate scope decision: no bundled ORM, no bundled email. See
[[docs/about/non-goals|Non-Goals]] and [[docs/about/philosophy|the philosophy behind these scope decisions]].

**Tokens stay stateless or app-owned.** A password-reset or email-verification
flow must carry its state in a stateless signed token (via `itsdangerous`, the
same primitive Chirp uses for session signing) or in a token store the app
provides. Chirp will not create a framework-owned, per-user token table — that
would force a schema, a migration, and a storage backend on every app. Signed
tokens need no storage; an app-provided store keeps the schema decision with the
app that owns its database.

**Email is a bring-your-own callback, never a bundled mailer.** A flow renders its
message body as a Kida template and hands the rendered HTML to an app-provided
mailer callback. Chirp will not bundle an SMTP client. This mirrors the existing
auth extension seams: `AuthConfig` already takes `load_user` and `verify_token` as
app-supplied async callbacks. Chirp renders the HTML; the app decides how to send
it — SMTP, a provider API, or a queue.
:::

:::{note} See also
- [[docs/quality/deployment/production|Production deployment]] — the rest of the ship-to-prod checklist
- [[docs/quality/contracts-debugging/categories|Contract categories]] — the env-aware severity model these items map to
- [[docs/quality/contracts-debugging/route-contract|The route and security-stack contract]] — how `app.check()` enforces the secure-by-default stack
- [[docs/quality/testing/_index|Testing]] — verify your hardened stack before you ship
:::
