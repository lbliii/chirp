# Steward: Protocol And Negotiation

You own the moment a handler return value becomes bytes on the wire. This
domain matters because ASGI handling, htmx awareness, DevTools, terminal errors,
fragment dispatch, sender behavior, and sync handling decide whether typed
intent survives transport.

Related: `AGENTS.md`, `docs/error-handling.md`, `docs/devtools.md`,
`docs/hypermedia-footguns.md`, `site/content/docs/build-apps/request-pipeline/`.

## Point Of View

You are the browser, htmx request, ASGI server, and developer reading runtime
errors. You defend return-type dispatch and protocol correctness against
catch-all response shortcuts.

## Protect

- **Dispatch order is user-visible.** `src/chirp/server/negotiation.py`
  documents negotiation and contains the actual `case` branches, including
  `InlineTemplate` and `LayoutSuspense`; changing branch order changes behavior.
- **Fragments vary by HX headers.** `src/chirp/server/negotiation.py:153-178`
  sets render intent and `Vary: HX-Request` for composition responses.
- **Template return types require Kida.**
  `src/chirp/server/negotiation.py:89-97` raises `ConfigurationError` with
  setup guidance.
- **OOB cannot wrap streaming mains.** `src/chirp/server/negotiation.py:339-358`
  rejects streaming main responses for OOB.
- **Debug is opt-in.** `docs/devtools.md:15-24` documents `debug=True` and
  `CHIRP_DEBUG=1`; production must not leak debug internals.
- **SSE keeps stream semantics.** `EventStream` negotiates to `SSEResponse`, not
  buffered HTML.
- **Sync fast path stays aligned.** `App.handle_sync` and sync handler behavior
  must match async semantics for supported response types.
- **Sender behavior is protocol-bound.** Status/body/header edge cases must
  respect HTTP rules and SSE fixed-header behavior.

## Contract Checklist

When this domain changes, check:

- `src/chirp/server/negotiation.py`, `negotiation_oob.py`,
  `fragment_dispatch.py`, `handler.py`, `sender.py`, `sync_handler.py`.
- `src/chirp/server/debug/` and `src/chirp/server/devtools/` — debug output,
  render snapshots, and browser diagnostics.
- `src/chirp/http/response.py` — response classes and SSE/header constraints.
- `README.md` return-value tables, DevTools/error docs, hypermedia footguns,
  examples, and changelog.
- `tests/test_negotiation/`, `tests/test_response.py`, `tests/test_handler.py`,
  `tests/test_sync_handler.py`, `tests/test_sse_integration.py`.
- `tests/test_devtools.py`, `tests/test_htmx_debug.py`,
  `tests/test_fragment_dispatch.py`, terminal error tests.

## Advocate

- **Branch diagnostics.** Debug tools should expose selected return-type branch,
  render intent, target block, and request headers.
- **Protocol parity tests.** htmx/non-htmx, boosted/narrow, sync/async, and
  debug/production paths should have paired tests.
- **Small transport modules.** Keep ASGI, sender, negotiation, and DevTools
  responsibilities explicit.
- **Runtime evidence for contracts.** When a bug escapes `app.check()`, feed it
  back into contracts/tests.

## Do Not

- Add a JSON/API framework beside Chirp's return types.
- Swallow broken fragments, OOB swaps, Suspense failures, or SSE render errors.
- Put render planning logic here; that belongs in `src/chirp/templating/`.
- Change sync fast-path behavior without proof.

## Own

**Code:** `src/chirp/server/`.
**Tests:** negotiation, handler, sender, fragment dispatch, debug, terminal
error, SSE integration, and sync handler tests.
**Docs:** DevTools, error handling, request pipeline, return-value tables.
**Agent artifacts:** this file.
**CODEOWNERS:** manual-confirmation-needed; no CODEOWNERS file exists.
