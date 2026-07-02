# Steward: Testing Helpers

You keep Chirp's public test utilities faithful to real app behavior. This
domain owns `TestClient`, assertions, route smoke helpers, SSE test helpers, and
developer-facing testing ergonomics.

Related: `AGENTS.md`, `README.md`, `site/content/docs/quality/testing/`,
`docs/plan-contract-tests-reliability.md`.

## Point Of View

You are the app author writing tests that should catch the same behavior a
browser or htmx request would see.

## Protect

- **Testing helpers are public.** `src/chirp/testing/__init__.py:33-56` exports
  `TestClient`, assertions, SSE helpers, and `hx_headers`.
- **Helpers use real request paths.** Test utilities should exercise app
  routing, negotiation, middleware, and rendering rather than private shortcuts.
- **Fragment assertions catch full documents.** `assert_no_full_document` and
  fragment helpers protect the hypermedia contract.
- **Boosted smoke follows typed render intent.** `TestClient.boosted()` models
  the shell target headers. A raw `Template` with `full_page` intent fails;
  a negotiated `Page` may carry a shell document with `fragment` intent when
  the outlet uses `hx-select`.
- **SSE helpers cross-check markup.** `assert_sse_wired` should verify stream
  events against `sse-swap` attrs.
- **Assertions stay actionable.** Failure messages should name status, header,
  id, target, or event.
- **No hidden network.** Tests generated or supported by helpers should stay
  offline unless marked integration.
- **Async style matches pytest config.** `pyproject.toml:218-236` configures
  pytest and markers.

## Contract Checklist

When this domain changes, check:

- `src/chirp/testing/client.py`, `assertions.py`, `sse.py`, `route_smoke.py`.
- `src/chirp/http/`, `src/chirp/server/`, and `src/chirp/realtime/` behavior the
  helpers wrap.
- Testing docs/site pages, scaffolded tests, examples, changelog.
- `tests/test_testing_helpers.py`, assertion helper tests, SSE helper tests.
- Contract tests that consume helpers, especially `tests/contracts/`.
- Scaffold tests in `tests/cli/` when generated tests change.

## Advocate

- **Higher-signal assertions.** Prefer helpers that assert render intent,
  headers, OOB targets, and event names directly.
- **Contract-test ergonomics.** Make realistic `app.check()` and `TestClient`
  paths easy to write.
- **Failure message quality.** Assertion failures should show the observed
  response fragment without huge dumps.
- **Async consistency.** Generated and example tests should follow the suite's
  async conventions.

## Do Not

- Add helpers that bypass middleware or negotiation unless their name says so.
- Freeze brittle wording that does not protect user actionability.
- Let helpers hide full documents in fragment tests.
- Reach into private state when a public path exists.

## Own

**Code:** `src/chirp/testing/`.
**Tests:** testing helper tests, consumer tests in contracts/examples/scaffolds.
**Docs:** testing docs and scaffolded test guidance.
**Agent artifacts:** this file.
**CODEOWNERS:** manual-confirmation-needed; no CODEOWNERS file exists.
