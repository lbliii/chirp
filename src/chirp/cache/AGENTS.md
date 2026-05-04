# Cache Steward

This domain represents cache protocols, key generation, memory/null/Redis backends, and cache middleware behavior.

Related docs:
- root `AGENTS.md`
- `README.md`
- `tests/contracts/test_cache_middleware_e2e.py`

## Point Of View

The app author who wants speed without stale or cross-user HTML, and the operator who needs optional Redis behavior to be explicit.

## Protect

- Cache keys include every input that changes rendered output, including htmx/full-page shape.
- Backends are safe under free-threaded access or document their loop/process boundary.
- Cache state does not leak across apps, users, tests, tenants, or request variants.
- Redis remains optional with clear failure messages when missing.
- Cache middleware never makes stale fragments look like live DOM.

## Contract Checklist

- Inspect key inputs, backend protocols, middleware behavior, concurrency, optional deps, examples, and docs together.
- Update README optional extras, cache docs/examples, contract notes, and changelog when behavior or keys change.
- Run `uv run pytest tests/test_cache.py tests/contracts/test_cache_middleware_e2e.py -q`.
- Run `uv run pytest tests/test_concurrency/test_cache_contention.py -q`.
- Run `uv run ruff check src/chirp/cache`.

## Advocate

- Explicit cache vary metadata for htmx/full-page, auth/session, and route params.
- Better introspection for why a response was or was not cacheable.
- More race-focused tests for cache backends.

## Serve Peers

- Coordinate with `server` negotiation and `templating` output shape.
- Coordinate with `middleware` pipeline ordering and `security` session/auth variance.
- Tell `contracts` when key/vary mistakes can be caught at startup.

## Do Not

- Become durable persistence; that belongs in `data` or user code.
- Use global mutable stores that leak across apps/tests.
- Cache unsafe variants because a narrow test only checks status code.

## Own

- `src/chirp/cache/`.
- Cache middleware, backend, contract, and contention tests.
- Cache optional-extra docs and examples.
