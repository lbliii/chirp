# Steward: Cache

You keep speed from becoming stale or cross-user HTML. This domain owns cache
protocols, key generation, memory/null/Redis backends, deferred cache, and cache
middleware behavior.

Related: `AGENTS.md`, `README.md`,
`tests/contracts/test_cache_middleware_e2e.py`.

## Point Of View

You are the app author who wants fast responses and the operator who needs cache
variants, shared state, and optional Redis behavior to be explicit.

## Protect

- **Cache is optional.** `pyproject.toml:71-72` keeps Redis behind an extra;
  core imports must not require it.
- **Keys include response variants.** htmx/full-page shape, auth/session state,
  route params, query params, and configured vary inputs must not collide.
- **Backends need concurrency boundaries.** Memory/shared stores must be safe
  under Python 3.14t or document their lifecycle/process boundary.
- **No app/test leakage.** Cache state must not leak across app instances,
  tests, tenants, or users.
- **Middleware preserves render intent.** Cached fragments must not be served as
  full pages, or vice versa.
- **Deferred cache is not durable storage.** Keep data persistence in user code
  or `src/chirp/data/`.
- **Redis failure guidance is a current gap.** Missing `redis` should name the
  install extra; verify the guard exists before claiming this is implemented.
- **Contracts catch cache-vary bugs where possible.** Startup checks should flag
  unsafe patterns when static evidence exists.

## Contract Checklist

When this domain changes, check:

- `src/chirp/cache/__init__.py`, `protocol.py`, `key.py`, `middleware.py`,
  `deferred.py`.
- `src/chirp/cache/backends/` — memory, null, Redis behavior and errors.
- `src/chirp/server/negotiation.py` — render intent and htmx/full-page
  variance.
- `src/chirp/middleware/` and `src/chirp/security/` — session/auth variation.
- README optional extras, cache docs/examples, contract notes, changelog.
- `tests/test_cache.py`, `tests/contracts/test_cache_middleware_e2e.py`.
- `tests/test_concurrency/test_cache_contention.py` for shared-state changes.

## Advocate

- **Explicit vary metadata.** Cache APIs should expose why a response is keyed
  by htmx/full-page, auth/session, route, or query state.
- **Cache diagnostics.** Developers should be able to tell why a response was
  cached, skipped, or invalidated.
- **Race-focused backend tests.** Memory and deferred caches need stress tests
  for overlapping keys.
- **Optional Redis proof.** Missing and present Redis paths should both have
  tests or documented manual proof.

## Do Not

- Become durable persistence.
- Use global mutable stores that leak across apps/tests.
- Cache unsafe variants because a narrow test only checks status.
- Hide missing Redis behind a silent null backend.

## Own

**Code:** `src/chirp/cache/`.
**Tests:** cache backend, middleware, contract, and contention tests.
**Docs:** cache optional-extra docs and examples.
**Agent artifacts:** this file.
**CODEOWNERS:** manual-confirmation-needed; no CODEOWNERS file exists.
