# AGENTS.md

## Steward: Cache Steward

This domain protects cache protocols, key generation, memory/null/Redis backends, and cache
middleware behavior.

## Must Not Become

- A global mutable store that leaks data across apps or tests.
- A correctness risk where stale fragments masquerade as live HTML.
- A second persistence layer; durable data belongs in `data` or user code.

## Documentation Ownership

Update README optional extras, cache docs/examples, and contract notes when cache behavior or keys
change.

## Local Checks

Start with:

- `uv run pytest tests/test_cache.py tests/contracts/test_cache_middleware_e2e.py -q`
- `uv run pytest tests/test_concurrency/test_cache_contention.py -q`
- `uv run ruff check src/chirp/cache`

## Public Contracts And Safety Boundaries

- Cache keys must include every input that changes rendered output, including htmx/full-page shape.
- Backends must be safe under free-threaded access or document their loop/process boundary.
- Redis remains an optional extra with clear failure messages when missing.
