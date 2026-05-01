# AGENTS.md

## Steward: Testing Helpers Steward

This domain protects `TestClient`, assertion helpers, SSE testing utilities, and public testing
ergonomics for Chirp app authors.

## Must Not Become

- A private shortcut that depends on app internals staying mutable.
- A test-only behavior fork from real ASGI/request handling.
- A helper layer that makes broken hypermedia look green.

## Documentation Ownership

Update README, testing docs, and public API docs when helper APIs or assertions change.

## Local Checks

Start with:

- `uv run pytest tests/test_testing_helpers.py tests/test_app/test_e2e.py -q`
- `uv run pytest tests/test_sse_integration.py tests/contracts -q` when helper behavior affects contracts
- `uv run ruff check src/chirp/testing`

## Public Contracts And Safety Boundaries

- Test helpers should exercise the same return negotiation and contract paths users hit in apps.
- Assertions should fail with actionable detail, not just mismatched strings.
- Keep helpers small; app behavior belongs in runtime tests, not helper magic.
