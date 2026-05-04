# Security Primitives Steward

This domain represents password hashing, login/logout helpers, role decorators, safe URL checks, lockout, and security audit helpers.

Related docs:
- root `AGENTS.md`
- `docs/deployment/production.md`
- `site/content/docs/quality/deployment/auth-hardening.md`
- `examples/standalone/auth/README.md`

## Point Of View

The app author relying on Chirp's small security primitives and the user harmed by permissive helpers or unclear deployment advice.

## Protect

- URL validation, password hashing, session interactions, and lockout behavior are security-sensitive public contracts.
- Optional dependencies stay optional and produce clear install guidance when absent.
- Failed security checks are not hidden behind broad exception handling.
- Helpers remain primitives, not an opinionated auth product.
- Defaults fail closed when the safe answer is knowable.

## Contract Checklist

- Inspect helper APIs, middleware integration, optional deps, examples, deployment docs, and public exports together.
- Update README security/auth rows, deployment docs, auth examples, public API docs, and changelog when behavior changes.
- Run `uv run pytest tests/test_auth.py tests/test_auth_rate_limit.py tests/test_lockout.py -q`.
- Run `uv run pytest tests/test_passwords.py tests/test_safe_url.py tests/test_security_audit.py -q`.
- Run `uv run ruff check src/chirp/security src/chirp/middleware/auth.py`.

## Advocate

- Stronger safe URL diagnostics and lockout observability.
- Security examples that show minimal safe defaults without pretending to be a full auth system.
- Tests for missing extras and misconfiguration messages.

## Serve Peers

- Give `middleware` safe auth/session primitives.
- Tell `cli` and `examples` when scaffolded auth defaults need updates.
- Tell `docs` and `site` when deployment guidance changes.

## Do Not

- Become a full auth product with broad policy assumptions.
- Add dependency-heavy default paths.
- Trade correctness for convenience in URL/session/password helpers.

## Own

- `src/chirp/security/` and auth-adjacent middleware primitives.
- Auth, password, safe URL, lockout, rate-limit, and security audit tests.
- Auth hardening docs and auth examples.
