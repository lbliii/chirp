# AGENTS.md

## Steward: Middleware Pipeline Steward

This domain protects middleware protocols and built-ins: CORS, sessions, CSRF, auth integration,
allowed hosts, static files, CSP nonce, security headers, injection, and debug middleware.

## Must Not Become

- A place where middleware mutates shared request/global state without isolation.
- A silent security bypass hidden behind permissive defaults.
- A catch-all layer for route, rendering, or app lifecycle behavior.

## Documentation Ownership

Update README middleware rows, deployment/security docs, and examples when built-in middleware
behavior or setup changes.

## Local Checks

Start with:

- `uv run pytest tests/test_cors.py tests/test_csrf.py tests/test_sessions.py -q`
- `uv run pytest tests/test_allowed_hosts.py tests/test_static.py tests/test_security_headers.py -q`
- `uv run pytest tests/test_auth.py tests/test_auth_rate_limit.py tests/test_csp_nonce.py -q`

## Public Contracts And Safety Boundaries

- Middleware order is user-visible; changes can alter auth, CSRF, and htmx error behavior.
- Security middleware should fail closed with actionable configuration messages.
- Request-scoped helpers belong in context vars, not mutable module globals.
