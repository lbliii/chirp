# Protocol And Negotiation Steward

This domain represents ASGI handling, content negotiation, htmx awareness, debug pages, terminal errors, fragment dispatch, sync handling, sender behavior, and development server ergonomics.

Related docs:
- root `AGENTS.md`
- `docs/error-handling.md`
- `docs/devtools.md`
- `docs/hypermedia-footguns.md`
- `site/content/docs/build-apps/request-pipeline/`

## Point Of View

The browser, htmx request, ASGI server, and developer reading runtime errors when a returned value becomes bytes on the wire.

## Protect

- Return type dispatch order remains user-visible architecture.
- htmx fragment requests do not receive full HTML documents in narrow swap targets.
- Debug mode gives useful internals; production mode does not leak implementation details.
- SSE keeps per-event error boundaries unless a deliberate design change says otherwise.
- Sync handling stays fast and semantically aligned with async handling.

## Contract Checklist

- Inspect negotiation, htmx detection, fragment dispatch, errors, sender behavior, debug tooling, and sync path together.
- Update README return-value tables, DevTools/error docs, request-pipeline site docs, examples, and changelog when protocol behavior changes.
- Run `uv run pytest tests/test_response.py tests/test_negotiation tests/test_handler.py -q`.
- Run `uv run pytest tests/test_sync_handler.py tests/test_sse_integration.py tests/test_terminal_errors.py -q`.
- Run `uv run pytest tests/test_devtools.py tests/test_htmx_debug.py tests/test_fragment_dispatch.py -q`.

## Advocate

- Diagnostics that show request headers, selected return-type branch, target block, and next action.
- Small protocol modules with explicit contracts instead of broad handler branches.
- Parity tests for htmx/non-htmx and async/sync entrypoints.

## Serve Peers

- Give `templating` exact render intents and propagate fail-loud rendering errors.
- Give `contracts` runtime evidence when startup checks miss a case.
- Give `testing` helpers the real request path.
- Give `cli` and `app` consistent startup and terminal error behavior.

## Do Not

- Bolt on a JSON/API framework beside Chirp's return types.
- Swallow broken fragments, OOB swaps, or SSE render errors.
- Put render planning logic here; that belongs in `templating`.

## Own

- `src/chirp/server/`.
- Negotiation, handler, sender, fragment dispatch, debug, terminal error, SSE integration, and sync handler tests.
- DevTools, error-handling, and request-pipeline docs.
