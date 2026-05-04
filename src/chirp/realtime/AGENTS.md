# Realtime Steward

This domain represents SSE event types, `EventStream`, and realtime protocol helpers that feed server-push UI after a page has loaded.

Related docs:
- root `AGENTS.md`
- `README.md`
- `site/content/docs/build-apps/streaming-updates/server-sent-events.md`
- `examples/standalone/sse/README.md`

## Point Of View

The user watching a long-lived realtime page and the app author expecting each event to render independently without killing the stream.

## Protect

- SSE remains for post-load updates, not initial render streaming.
- Heartbeat, disconnect cleanup, retry/id/event formatting, and per-event render boundaries are preserved.
- `SSEEvent` and Fragment-yield semantics are public return-type behavior.
- One bad event does not quietly silence an hours-long stream.
- Reactive event helpers do not introduce shared-state races.

## Contract Checklist

- Inspect event formatting/parsing, EventStream behavior, fragment payloads, lifecycle cleanup, reactive interaction, docs, and examples together.
- Update README streaming tables, SSE docs, examples, hypermedia footguns, and changelog when event behavior changes.
- Run `uv run pytest tests/test_sse_parser.py tests/test_sse_integration.py tests/test_sse_macros.py -q`.
- Run `uv run pytest tests/contracts/test_sse.py tests/test_reactive_stream.py -q`.
- Run `uv run pytest examples/standalone/sse -q`.

## Advocate

- Better stream diagnostics for disconnects, render errors, and retry behavior.
- Examples that clearly separate `Stream`, `Suspense`, and `EventStream`.
- Tests for long-lived stream boundaries and malformed events.

## Serve Peers

- Give `server` event lifecycle hooks that preserve protocol correctness.
- Give `templating` fragment payload contracts for SSE.
- Give `pages` reactive flows and `examples` realistic post-load updates.

## Do Not

- Become a WebSocket abstraction.
- Replace `Stream` or `Suspense` initial rendering.
- Widen per-event failures to the whole stream without a design check-in.

## Own

- `src/chirp/realtime/` and SSE event contracts.
- SSE parser, integration, macro, contract, and reactive stream tests.
- SSE docs and realtime examples.
