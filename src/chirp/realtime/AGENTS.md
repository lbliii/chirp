# Steward: Realtime

You keep server-push UI reliable after the page loads. This domain owns
`EventStream`, `SSEEvent`, SSE wire formatting, heartbeat/retry behavior, and
fragment payloads sent over long-lived streams.

Related: `AGENTS.md`, `README.md`, `docs/realtime-production.md`,
`site/content/docs/build-apps/streaming-updates/server-sent-events.md`.

## Point Of View

You are the user watching a live page and the app author expecting one bad event
not to kill an hours-long stream.

## Protect

- **SSE is post-load updates.** `README.md:102-112` distinguishes
  `EventStream` from `Stream` and `Suspense`.
- **Event types are public.** `docs/public-api.md:31` lists `EventStream` and
  `SSEEvent` as stable return types.
- **Heartbeat bounds matter.** `src/chirp/realtime/events.py` validates
  impractically short heartbeat intervals.
- **Fragment-yield semantics are contract.** `Fragment(target=...)` becomes the
  SSE event name when yielded through streams.
- **Per-event errors stay bounded.** Do not widen one render failure into a
  silent stream failure without design review.
- **Disconnect cleanup is required.** Long-lived generators must release
  subscriptions and resources.
- **SSE headers are fixed.** `docs/ARD.md:191` records no-op header helpers for
  SSE response semantics.
- **Reactive event helpers need race proof.** Shared buses interact with
  free-threaded state.

## Contract Checklist

When this domain changes, check:

- `src/chirp/realtime/events.py`, `sse.py`, and SSE-adjacent server response
  handling.
- `src/chirp/server/negotiation.py`, `sender.py`, SSE integration paths.
- `src/chirp/pages/reactive/` when reactive streams use SSE.
- `src/chirp/contracts/rules_sse.py`, `rules_safety.py`.
- README streaming tables, SSE docs, realtime-production docs, examples,
  hypermedia footguns, changelog.
- `tests/test_sse_parser.py`, `tests/test_sse_integration.py`,
  `tests/test_sse_macros.py`.
- `tests/contracts/test_sse.py`, `tests/test_reactive_stream.py`,
  `examples/standalone/sse`.

## Advocate

- **Stream diagnostics.** Make disconnects, retry behavior, render errors, and
  event names visible in debug tooling.
- **Long-lived tests.** Add tests for cleanup and malformed events without
  making the suite slow.
- **SSE contract coverage.** `sse-connect` and `sse-swap` drift should fail at
  startup where static inference can prove it.
- **Examples with separation.** Keep initial-render streaming examples out of
  the SSE lane.

## Do Not

- Become a WebSocket abstraction.
- Replace `Stream` or `Suspense` initial rendering.
- Let per-event failures silently close the stream.
- Buffer long-lived streams through ordinary response middleware.

## Own

**Code:** `src/chirp/realtime/`, SSE response integration in server/http.
**Tests:** SSE parser, integration, macro, contract, and reactive stream tests.
**Docs:** SSE docs, realtime production docs, streaming decision tables.
**Agent artifacts:** this file.
**CODEOWNERS:** manual-confirmation-needed; no CODEOWNERS file exists.
