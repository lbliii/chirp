# Testing Helpers Steward

This domain represents `TestClient`, assertion helpers, SSE testing utilities, and public testing ergonomics for Chirp app authors.

Related docs:
- root `AGENTS.md`
- `site/content/docs/quality/testing/`
- `docs/public-api.md`

## Point Of View

The app developer writing tests and the framework maintainer ensuring helpers exercise real runtime behavior instead of a test-only shortcut.

## Protect

- Test helpers follow the same return negotiation and contract paths users hit in apps.
- Assertions fail with actionable detail, not just mismatched strings.
- SSE helpers preserve event boundaries and stream semantics.
- Helpers do not depend on app internals staying mutable after freeze.
- Helper convenience does not make broken hypermedia look green.

## Contract Checklist

- Inspect client request path, assertions, SSE helpers, public exports, docs, examples, and contract tests together.
- Update README, testing docs, public API docs, and changelog when helper APIs or assertions change.
- Run `uv run pytest tests/test_testing_helpers.py tests/test_app/test_e2e.py -q`.
- Run `uv run pytest tests/test_sse_integration.py tests/contracts -q` when helper behavior affects contracts.
- Run `uv run ruff check src/chirp/testing`.

## Advocate

- More helper assertions for fragments, OOB swaps, SSE events, and contract issues.
- Failure messages that name expected route/template/block/selector.
- Docs that teach testing realistic htmx vs full-page flows.

## Serve Peers

- Give `tests/contracts` reliable end-to-end helpers.
- Give `examples` simple smoke tests that still use real behavior.
- Tell `server`, `templating`, and `app` when helper ergonomics expose runtime friction.

## Do Not

- Fork behavior from real ASGI/request handling.
- Mutate frozen app internals for convenience.
- Hide response negotiation details in magic assertions.

## Own

- `src/chirp/testing/`.
- Testing helper, app e2e, SSE integration, and contract helper tests.
- Testing docs and helper examples.
