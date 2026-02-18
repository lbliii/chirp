---
title: Auth Hardening
description: Production checklist for authentication and authorization safety
draft: false
weight: 45
lang: en
type: doc
tags: [auth, security, hardening]
keywords: [auth hardening, csrf, sessions, csp, hsts, rate limit]
category: guide
---

## Production Checklist

Use this checklist before shipping paid or user-data-heavy applications.

### 1) Session and Cookies

- Set a strong `CHIRP_SECRET_KEY` from environment.
- Use `SessionConfig(secure=True, httponly=True, samesite="lax")` in production.
- Enable `idle_timeout_seconds` and `absolute_timeout_seconds` for session lifecycle control.
- Use `AuthConfig(session_version=...)` to invalidate stale sessions after password reset/account events.

### 2) CSRF and Forms

- Register middleware in order:
  1. `SessionMiddleware`
  2. `AuthMiddleware`
  3. `CSRFMiddleware`
- Include `{{ csrf_field() }}` in all unsafe forms.
- Keep `CSRFMiddleware` enabled for cookie-authenticated routes.

### 3) Authorization

- Use `@login_required` and `@requires(...)` for route-level checks.
- Add `policy=` callbacks for object-level ownership checks.
- Return 403 for unauthorized resources without leaking policy details.

### 4) Abuse Protection

- Add `AuthRateLimitMiddleware` for login/reset endpoints.
- Add lockout/backoff with `LoginLockout` in login handlers.
- Monitor repeated failures and blocked attempts with audit events.

### 5) Browser Security Headers

- Enable `SecurityHeadersMiddleware`.
- Configure a strict `Content-Security-Policy`.
- Configure `Strict-Transport-Security` when serving over HTTPS.
- Keep `X-Frame-Options`, `X-Content-Type-Options`, and `Referrer-Policy` defaults unless you have a reason to change them.

### 6) Password and Secrets

- Prefer argon2 (`pip install bengal-chirp[auth]`) in production.
- Use password reset and session version rotation on credential changes.
- Never commit secrets; rotate periodically.

### 7) Audit and Operations

- Register a sink via `set_security_event_sink(...)`.
- Alert on spikes in:
  - `auth.token.invalid`
  - `csrf.reject.*`
  - `authz.permission.denied`
- Keep backups and incident runbooks for account takeover response.

## Minimal Hardened Setup

```python
from chirp.middleware import (
    AuthRateLimitConfig,
    AuthRateLimitMiddleware,
    CSRFMiddleware,
    SecurityHeadersConfig,
    SecurityHeadersMiddleware,
    SessionConfig,
    SessionMiddleware,
)

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
app.add_middleware(AuthRateLimitMiddleware(AuthRateLimitConfig(paths=("/login", "/password-reset"))))
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
