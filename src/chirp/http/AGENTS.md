# AGENTS.md

## Steward: HTTP Primitives Steward

This domain protects immutable HTTP types: `Request`, `Response`, `JSONResponse`, cookies, forms,
headers, query params, and `SyncRequest`.

## Must Not Become

- Starlette-compatible by imitation instead of Chirp-native by contract.
- A place for template, app, or router dependencies.
- A mutable bag of request data shared across handlers.

## Documentation Ownership

Update README return-value examples, `docs/public-api.md`, and error-handling docs when request or
response behavior changes.

## Local Checks

Start with:

- `uv run pytest tests/test_request.py tests/test_response.py tests/test_headers.py -q`
- `uv run pytest tests/test_cookies.py tests/test_forms.py tests/test_sync_request.py -q`
- `uv run pytest tests/test_sync_handler.py -q` when sync request behavior changes

## Public Contracts And Safety Boundaries

- HTTP collections are immutable or copy-on-write.
- Header behavior must preserve multiple values where HTTP requires it, especially `Set-Cookie`.
- `Response` transformations should return new values or otherwise remain thread-safe.
- The sync fast path is performance-sensitive; measure and explain changes there.
