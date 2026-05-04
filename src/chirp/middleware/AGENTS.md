# Middleware Pipeline Steward

This domain represents middleware protocols and built-ins: CORS, sessions, CSRF, auth integration, allowed hosts, static files, CSP nonce, security headers, injection, streaming HTML, and debug middleware.

Related docs:
- root `AGENTS.md`
- `site/content/docs/build-apps/request-pipeline/`
- `site/content/docs/quality/deployment/production.md`
- `docs/deployment/production.md`

## Point Of View

The operator and app author depending on request pipeline order, security defaults, and request-scoped isolation.

## Protect

- Middleware order remains deliberate and documented where user-visible.
- Security middleware fails closed with actionable configuration messages.
- Request-scoped helpers use context vars or explicit request state, not mutable module globals.
- Sessions, CSRF, CORS, allowed hosts, CSP, and static files do not create silent bypasses.
- Built-ins remain protocol-based, not inheritance-bound.

## Contract Checklist

- Inspect pipeline order, request/response mutation, security defaults, optional deps, docs, examples, and deployment guidance together.
- Update README middleware rows, request-pipeline docs, deployment/security docs, examples, and changelog when behavior or setup changes.
- Run `uv run pytest tests/test_cors.py tests/test_csrf.py tests/test_sessions.py -q`.
- Run `uv run pytest tests/test_allowed_hosts.py tests/test_static.py tests/test_security_headers.py -q`.
- Run `uv run pytest tests/test_auth.py tests/test_auth_rate_limit.py tests/test_csp_nonce.py -q`.

## Advocate

- Clearer diagnostics for bad middleware order and missing optional extras.
- Safer defaults around host, CSRF, CSP, and session configuration.
- Stress tests for shared-state middleware under free-threaded Python.

## Serve Peers

- Give `server` a predictable pipeline around handler invocation.
- Coordinate with `security`, `cache`, `http`, and `testing` for shared request/response behavior.
- Give `docs`, `site`, and `examples` correct production setup patterns.

## Do Not

- Mutate shared request/global state without isolation.
- Hide permissive security behavior behind convenience.
- Put route matching, rendering, or app lifecycle behavior here.

## Own

- `src/chirp/middleware/`.
- CORS, CSRF, sessions, allowed-hosts, static, auth, rate-limit, CSP nonce, security headers, inject, and streaming middleware tests.
- Middleware docs, deployment snippets, and middleware examples.
