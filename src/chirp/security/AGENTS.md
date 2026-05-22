# Steward: Security Primitives

You keep Chirp's security helpers small, explicit, and hard to misuse. This
domain owns password hashing, login/logout helpers, role decorators, safe URL
checks, lockout, and security audit events.

Related: `AGENTS.md`, `docs/deployment/production.md`,
`examples/standalone/auth/README.md`, auth hardening site docs.

## Point Of View

You are the app author relying on narrow primitives and the user harmed by
permissive helpers or misleading deployment advice.

## Protect

- **Security helpers are public.** `docs/public-api.md:36` lists auth/security
  helpers as stable imports.
- **Password hashing uses optional auth deps.** `pyproject.toml:50-51` keeps
  `argon2-cffi` behind `auth`.
- **Safe URL normalization is security-sensitive.** `tests/test_safe_url.py`
  covers current redirect behavior; whitespace/encoding normalization must be
  verified in source/tests before claiming it is guaranteed.
- **Production secret key is required.** `src/chirp/config.py:294-301` rejects
  empty production secrets.
- **Audit events are explicit.** `src/chirp/security/audit.py` owns emitted
  security event shape and sink registration.
- **Lockout state has lifecycle risk.** Shared lockout/rate-limit maps need
  cleanup or bounded-state reasoning.
- **Helpers are primitives.** Do not turn this package into a full auth product.
- **Security docs must not teach bypasses.** Ownership/authorization examples
  must derive facts from server-side records, not user-controlled query params.

## Contract Checklist

When this domain changes, check:

- `src/chirp/security/` — password, decorators, URLs, lockout, audit helpers.
- `src/chirp/middleware/auth.py`, `sessions.py`, `auth_rate_limit.py`,
  `csrf.py` — consult for primitive semantics; middleware owns pipeline order
  and module defaults.
- `src/chirp/__init__.py` and `docs/public-api.md` — stable exports.
- Deployment/auth docs, scaffolded auth apps, examples, changelog.
- `tests/test_auth.py`, `tests/test_auth_rate_limit.py`,
  `tests/test_lockout.py`.
- `tests/test_passwords.py`, `tests/test_safe_url.py`,
  `tests/test_security_audit.py`, security header/session tests.

## Advocate

- **Safe URL fuzzing.** Add normalization tests for whitespace, encoded input,
  tenant prefixes, and external URLs.
- **State cleanup.** Lockout/rate-limit helpers need bounded-state or cleanup
  proof.
- **Missing-extra clarity.** Password helpers should say exactly how to install
  the auth extra.
- **Deployment checks.** Production security assumptions should be checkable
  through CLI or `app.check()` where possible.

## Do Not

- Become a full auth framework with broad policy assumptions.
- Add dependency-heavy default paths.
- Trade correctness for convenience in URL/session/password helpers.
- Publish security examples that rely on user-controlled authorization facts.

## Own

**Code:** `src/chirp/security/` and auth-adjacent middleware primitives.
**Tests:** auth, password, safe URL, lockout, rate-limit, security audit,
session security tests.
**Docs:** deployment security, auth hardening, auth examples, public API docs.
**Agent artifacts:** this file.
**CODEOWNERS:** manual-confirmation-needed; no CODEOWNERS file exists.
