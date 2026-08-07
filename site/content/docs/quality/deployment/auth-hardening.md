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

:::{tip}
New to Chirp auth? Start with [[docs/tutorials/auth-login-walkthrough|A Login That Is Correct by Default]] —
the whole login → gated page → logout loop in one copy-pasteable file, with the
secure stack wired and `app.check()` catching the one wire you forgot. Then come
back here for the production hardening checklist.
:::

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
`AuthRateLimitMiddleware` keys its rate-limit buckets off
`request.trusted_client_ip` — the trusted-proxy-corrected client IP. It never
reads a raw client-supplied `X-Forwarded-For` (which is spoofable: an attacker
rotating the first hop would otherwise win a fresh bucket on every request).
Behind a proxy, configure the proxy chain on Chirp's ASGI server (pounce)
`trusted_proxies` / `forwarded_for_trusted_hops` so `scope["client"]` carries
the real client address before the limiter sees it. To key on a different
trusted, server-set identity (e.g. an authenticated API-key header), set
`key_header`; it is consumed verbatim, never comma-split. For per-user or
per-resource limits, set `key_fn` to derive the key from a **server-side**
identity — never from a client-controlled value a caller could rotate.
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
* - Bearer-token revocation
  - Reject revoked bearer tokens (per-`jti` revoke + per-user `iat <= revoked_at` cutoff); the bearer-path analogue of `session_version`. Fails open on a store outage.
  - `AuthConfig(token_revocation_store=..., token_claims=...)`
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
  - Use argon2 in production; verify logins with the enumeration-safe primitive and upgrade stale hashes on login
  - `pip install bengal-chirp[auth]`; `verify_login(...)`, `verify_and_upgrade(...)`
* - Audit
  - Register a sink and alert on auth/CSRF/authz event spikes
  - `set_security_event_sink(...)`
:::

The authorization decorators and lockout helpers live in `chirp.security`, not
`chirp.middleware`:

```python
from chirp.security import LockoutConfig, LoginLockout, login_required, requires
```

### Per-record access grants

Resource-level grants live in an app-owned `access_grants` table. Use
`access_grants_ddl("sqlite")` or `access_grants_ddl("postgresql")` for the
migration SQL — do not copy SQLite-only `AUTOINCREMENT` / `last_insert_rowid()`
forms. `create_grant` inserts with portable `INSERT ... RETURNING`.

```python
from chirp.security import access_grants_ddl, create_grant

await db.execute_script(access_grants_ddl("postgresql"))  # or "sqlite"
```

### Password hashing and login verification

`chirp.security` ships the credential primitives. They live one import away:

```python
from chirp.security import (
    hash_password,
    verify_password,
    verify_login,
    verify_and_upgrade,
    needs_rehash,
)
```

**Hashing algorithm.** `hash_password` uses **argon2id** when `chirp[auth]`
(`argon2-cffi`) is installed and falls back to **stdlib scrypt** otherwise. Both
produce PHC-format strings, and `verify_password` auto-detects the algorithm from
the prefix — so a hash survives a later default change. argon2id is the
recommended production algorithm; the `password_extra` contract WARNs (in
staging/production) when a login surface ships without `argon2-cffi`. Install it
with `pip install chirp[auth]`. The argon2id cost factors are pinned in
`chirp.security.passwords` to RFC 9106 §4's memory-constrained option (`t=3`,
`m=64 MiB`, `p=4`) — auditable and stable across the dependency's defaults.

**Timing-safe login (kill the enumeration oracle).** The naive login check
`if user and verify_password(password, user.password_hash)` leaks a
**user-enumeration timing oracle**: when the username does not exist, no hash is
computed, so the request returns measurably faster than a wrong password for a
real account. An attacker times the difference to enumerate valid usernames.
`verify_login` closes this — pass `None` for an unknown user and it still runs a
full verify against a process-wide decoy hash before returning `False`, so the
unknown-user and wrong-password paths take comparable time:

```python
user = USERS.get(username)
if verify_login(password, user.password_hash if user else None):
    login(user)
    return Redirect("/dashboard")
return Template("login.html", error="Invalid username or password")
```

Always call `verify_login` (do not short-circuit on `user is None`), or the decoy
never runs. The decoy is computed once under a lock; subsequent logins read the
published value. The timing equivalence is approximate, not byte-constant: in a
mixed-algorithm corpus (legacy scrypt hashes while argon2 is the default) the
decoy's cost differs from a stored scrypt verify. Re-deriving stale hashes (next)
converges the corpus toward one algorithm over time.

**Rehash-on-login (opportunistic upgrade).** `verify_and_upgrade` verifies the
password and, when correct **and** the stored hash is below the current cost
parameters, returns a freshly computed replacement. It never re-derives a hash
for a wrong guess, so a failed login can never trigger a database write:

```python
ok, new_hash = verify_and_upgrade(password, user.password_hash)
if not ok:
    return reject()
if new_hash is not None:
    user.password_hash = new_hash  # persist the upgrade
```

`needs_rehash(phc_hash, *, upgrade_algorithm=False)` reports parameter staleness
on its own (argon2 `check_needs_rehash`; scrypt `n`/`r` below the current pinned
cost). The algorithm-upgrade clause — flagging a scrypt hash stale merely because
argon2 is now installed — is gated behind `upgrade_algorithm` and **off by
default**, so installing the `auth` extra does not trigger a fleet-wide
rehash-write storm. Opt in during a controlled migration window.

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
- [[docs/tutorials/auth-login-walkthrough|A Login That Is Correct by Default]] — the golden-path login loop, end to end
- [[docs/quality/deployment/production|Production deployment]] — the rest of the ship-to-prod checklist
- [[docs/quality/contracts-debugging/categories|Contract categories]] — the env-aware severity model these items map to
- [[docs/quality/contracts-debugging/route-contract|The route and security-stack contract]] — how `app.check()` enforces the secure-by-default stack
- [[docs/quality/testing/_index|Testing]] — verify your hardened stack before you ship
:::
