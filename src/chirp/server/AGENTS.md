# AGENTS.md

## Steward: Protocol And Negotiation Steward

This domain protects ASGI handling, content negotiation, htmx awareness, debug pages, terminal
errors, fragment dispatch, sync handling, sender behavior, and development server ergonomics.

## Must Not Become

- A JSON/API framework bolted beside Chirp's return types.
- A quiet failure layer that swallows broken fragments, OOB swaps, or SSE errors.
- A home for template planning logic that belongs in `templating`.

## Documentation Ownership

Update README return-value tables, `docs/error-handling.md`, `docs/devtools.md`,
`docs/hypermedia-footguns.md`, and deployment docs when protocol behavior changes.

## Local Checks

Start with:

- `uv run pytest tests/test_response.py tests/test_negotiation tests/test_handler.py -q`
- `uv run pytest tests/test_sync_handler.py tests/test_sse_integration.py tests/test_terminal_errors.py -q`
- `uv run pytest tests/test_devtools.py tests/test_htmx_debug.py tests/test_fragment_dispatch.py -q`

## Public Contracts And Safety Boundaries

- Return type dispatch order is user-visible architecture.
- htmx requests must not receive whole documents in narrow fragment swaps.
- SSE keeps per-event error boundaries; do not widen failures to the whole stream casually.
- Debug mode may reveal detail; production mode must not leak implementation internals.
