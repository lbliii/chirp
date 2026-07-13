<!-- generated from .stewards/manifest.toml — edit the manifest, not this file -->

# Steward: cache

Keep performance from becoming stale, cross-user, cross-app, or wrong-render-intent HTML.

Ordinary work: use this map directly with the root map and run only affected checks.
Do not open `.stewards/PROTOCOL.md` or `.stewards/manifest.toml` unless the task is an explicit review/audit or steward-network maintenance.

## Protects

| Invariant | Sev | Backing | Proof / anchor |
| --- | --- | --- | --- |
| Cache backends and middleware preserve render, auth, route, query, and app-instance variance. | P0 | machine-backed | `uv run pytest tests/test_cache.py tests/contracts/test_cache_middleware_e2e.py -q` (`cache-suite`) |

## Guardrails

- Cache keys include htmx/full-page, auth/session, route, query, and configured vary inputs.
- Redis stays optional and missing-extra failures are actionable.

## Edges

- varies-by → **server** (render intent)
- integrates → **middleware** (cache middleware)

## Owns

- **code:** `src/chirp/cache/`
- **tests:** `tests/test_cache.py`, `tests/contracts/test_cache_middleware_e2e.py`
- **docs:** `README.md`
