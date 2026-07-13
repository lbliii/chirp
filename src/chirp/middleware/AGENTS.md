<!-- generated from .stewards/manifest.toml — edit the manifest, not this file -->

# Steward: middleware

Guard middleware order, request isolation, streaming compatibility, and secure defaults.

Ordinary work: use this map directly with the root map and run only affected checks.
Do not open `.stewards/PROTOCOL.md` or `.stewards/manifest.toml` unless the task is an explicit review/audit or steward-network maintenance.

## Protects

| Invariant | Sev | Backing | Proof / anchor |
| --- | --- | --- | --- |
| Security, session, CSRF, CORS, host, static, and response middleware retain safe ordering and defaults. | P0 | machine-backed | `uv run pytest tests/test_cors.py tests/test_csrf.py tests/test_sessions.py tests/test_allowed_hosts.py tests/test_static.py tests/test_security_headers.py -q` (`middleware-suite`) |

## Guardrails

- CSP relaxations remain narrowly scoped; script-src never gains unsafe-inline.
- Static files reject path and symlink traversal.
- Middleware does not buffer SSE or streaming HTML by accident.

## Edges

- uses → **security** (auth, CSRF, session, and audit primitives)
- wraps → **server** (request pipeline)

## Owns

- **code:** `src/chirp/middleware/`
- **tests:** `tests/test_csrf.py`, `tests/test_sessions.py`, `tests/test_static.py`, `tests/test_security_headers.py`
- **docs:** `docs/deployment/production.md`
