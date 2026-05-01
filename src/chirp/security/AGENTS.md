# AGENTS.md

## Steward: Security Primitives Steward

This domain protects password hashing, login/logout helpers, role decorators, URL safety, lockout,
and security audit helpers.

## Must Not Become

- A full auth product with policy assumptions Chirp cannot own.
- A permissive helper layer that trades correctness for convenience.
- A dependency-heavy default path; optional extras must remain deliberate.

## Documentation Ownership

Update README security/auth rows, deployment docs, examples, and public API docs when auth helpers
or safety behavior changes.

## Local Checks

Start with:

- `uv run pytest tests/test_auth.py tests/test_auth_rate_limit.py tests/test_lockout.py -q`
- `uv run pytest tests/test_passwords.py tests/test_safe_url.py tests/test_security_audit.py -q`
- `uv run ruff check src/chirp/security src/chirp/middleware/auth.py`

## Public Contracts And Safety Boundaries

- URL validation, password hashing, and session interactions are security-sensitive public behavior.
- Optional dependencies stay optional and produce clear install guidance when absent.
- Do not hide failed security checks behind broad exception handling.
