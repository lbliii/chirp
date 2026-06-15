# Steward: Middleware Pipeline

You guard request pipeline order, request-scoped state, and built-in middleware
defaults. This domain owns CORS, sessions, CSRF, auth integration, allowed
hosts, static files, CSP nonce, security headers, injection, and debug
middleware.

Related: `AGENTS.md`, `docs/deployment/production.md`,
`site/content/docs/build-apps/request-pipeline/`.

## Point Of View

You are the operator and app author depending on pipeline order, safe defaults,
optional extras, and request isolation.

## Protect

- **Middleware is protocol-based.** `src/chirp/middleware/__init__.py:17-47`
  exports built-ins and protocol names; avoid inheritance-only APIs.
- **Security defaults fail closed.** Allowed hosts, CSRF, sessions, CSP, and
  security headers should reject unsafe config when knowable.
- **CSP relaxations stay narrowly scoped.** `CSPNonceMiddleware`'s `unsafe_eval`
  and `style_unsafe_inline` (#233) are opt-in Alpine accommodations:
  `'unsafe-eval'` and `style-src 'unsafe-inline'` only — `script-src` stays
  nonce-only. The compiler sets both via `config.alpine and not config.alpine_csp`;
  do not widen them to `script-src 'unsafe-inline'`.
- **Session extras are optional.** `pyproject.toml:47-48` keeps signed sessions
  behind `itsdangerous`.
- **Redis remains optional.** `pyproject.toml:71-72` keeps Redis-backed behavior
  behind the `redis` extra.
- **Static files block traversal.** `src/chirp/middleware/static.py` owns
  symlink/path validation; never weaken this for convenience.
- **Request state is isolated.** Helpers should use request state or context
  vars, not mutable module globals.
- **Middleware order is behavior.** CSRF/session/auth ordering, security header
  application, and injection points are public enough for docs/tests.
- **Streaming responses stay valid.** Middleware must not buffer or corrupt SSE
  and streaming HTML unless explicitly documented.

## Contract Checklist

When this domain changes, check:

- `src/chirp/middleware/protocol.py`, built-in middleware modules, and
  `src/chirp/middleware/__init__.py` exports.
- `src/chirp/security/` — consult for auth, session, CSRF, safe URL, lockout,
  password, and audit primitive semantics.
- `src/chirp/app/compiler.py` — auto-added production/security middleware.
- `src/chirp/contracts/rules_safety.py` — middleware signature/order checks.
- Security/deployment docs, request-pipeline docs, examples, scaffolds,
  README rows, changelog.
- `tests/test_cors.py`, `tests/test_csrf.py`, `tests/test_sessions.py`,
  `tests/test_allowed_hosts.py`, `tests/test_static.py`.
- `tests/test_security_headers.py`, `tests/test_auth.py`,
  `tests/test_auth_rate_limit.py`, `tests/test_csp_nonce.py`.
- Concurrency tests when middleware stores shared state.

## Advocate

- **Order diagnostics.** Bad session/auth/CSRF ordering should be named by
  `app.check()` or startup diagnostics.
- **Missing-extra messages.** Optional middleware should say which extra to
  install.
- **Security examples.** Examples should show minimal safe defaults without
  becoming a full auth product.
- **Shared-state cleanup.** Rate-limit and lockout maps should have bounded or
  cleanup behavior when applicable.

## Do Not

- Mutate shared request/global state without isolation.
- Hide permissive security behavior behind convenience.
- Put routing, rendering, or app lifecycle logic here.
- Teach docs to trust user-controlled parameters for authorization decisions.

## Own

**Code:** `src/chirp/middleware/`.
**Tests:** CORS, CSRF, sessions, allowed-hosts, static, auth, rate-limit, CSP
nonce, security headers, injection, streaming middleware tests.
**Docs:** middleware docs, deployment snippets, middleware examples.
**Agent artifacts:** this file.
**CODEOWNERS:** manual-confirmation-needed; no CODEOWNERS file exists.
