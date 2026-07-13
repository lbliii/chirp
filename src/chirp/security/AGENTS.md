<!-- generated from .stewards/manifest.toml — edit the manifest, not this file -->

# Steward: security

Keep authentication, authorization, audit, password, redirect, and lockout primitives explicit and hard to misuse.

Ordinary work: use this map directly with the root map and run only affected checks.
Do not open `.stewards/PROTOCOL.md` or `.stewards/manifest.toml` unless the task is an explicit review/audit or steward-network maintenance.

## Protects

| Invariant | Sev | Backing | Proof / anchor |
| --- | --- | --- | --- |
| Imperative and declarative auth gates preserve canonical denial behavior and audit payload parity. | P0 | machine-backed | `uv run pytest tests/test_auth.py tests/test_auth_parity.py tests/test_auth_rate_limit.py tests/test_auth_scopes.py tests/test_passwords.py tests/test_safe_url.py tests/test_security_audit.py -q` (`security-suite`) |
| All supported auth styles delegate to one enforce_auth implementation. | P0 | manual | src/chirp/security/auth_core.py · `def enforce_auth` |
| Unauthenticated auth denial emits the canonical auth.require.unauthenticated event. | P0 | manual | src/chirp/security/auth_core.py · `auth.require.unauthenticated` |

## Guardrails

- Imperative decorators and declarative RouteMeta.auth delegate to one enforce_auth gate and preserve canonical audit payloads.
- Unregistered named policy is misconfiguration: raise LookupError, emit no denial event.
- Unauthenticated emits auth.require.unauthenticated with {}; permission denial emits authz.permission.denied with sorted missing names, or reason=missing_permissions_protocol plus sorted missing names.
- A resolved falsy named policy emits authz.policy.denied with its referenced policy identifier; an unresolved name raises LookupError and emits nothing.
- Machine scope denial emits authz.scope.denied with sorted missing names, or reason=missing_scopes_protocol plus sorted missing names; scope-name equality uses secrets.compare_digest.
- http.request is a single-producer AuditMiddleware event whose details preserve status_code, trusted source_ip, user_agent, and request-level body/body_omitted semantics.
- Bearer revocation checks fail open on store or claim errors; revoked events preserve jti or user_cutoff reason payloads and check errors expose only the exception class name.

## Edges

- integrated-by → **middleware** (auth and request pipeline)
- verified-by → **contracts** (auth_spec and security rules)

## Owns

- **code:** `src/chirp/security/`, `src/chirp/middleware/auth.py`
- **tests:** `tests/test_auth.py`, `tests/test_auth_parity.py`, `tests/test_safe_url.py`, `tests/test_security_audit.py`
- **docs:** `docs/deployment/production.md`, `examples/standalone/auth/`

## Advocate

- Parity locks, constant-time comparisons, bounded shared state, fuzzed safe URLs, and deployment checks.

## Do Not

- Broaden policy assumptions, hide permissive fallbacks, or publish authorization examples based on user-controlled facts.
