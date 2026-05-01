# AGENTS.md

## Steward: Realtime Steward

This domain protects SSE event types, `EventStream`, and realtime protocol helpers that feed
server-push UI after a page has loaded.

## Must Not Become

- A WebSocket abstraction.
- A replacement for initial-render streaming; that is `Stream` or `Suspense`.
- A stream where one broken event can quietly kill hours of updates.

## Documentation Ownership

Update README streaming tables, `docs/error-handling.md`, SSE examples, and hypermedia footguns
when event behavior changes.

## Local Checks

Start with:

- `uv run pytest tests/test_sse_parser.py tests/test_sse_integration.py tests/test_sse_macros.py -q`
- `uv run pytest tests/contracts/test_sse.py tests/test_reactive_stream.py -q`
- `uv run pytest examples/standalone/sse -q`

## Public Contracts And Safety Boundaries

- SSE is for post-load updates; do not blur it with Suspense initial rendering.
- Preserve heartbeat, disconnect cleanup, and per-event render boundaries.
- `SSEEvent` and Fragment-yield semantics are public return-type behavior.
