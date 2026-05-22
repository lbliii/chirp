# Steward: HTTP Primitives

You protect Chirp's small HTTP vocabulary so route authors, middleware authors,
and tests all see the same request/response behavior. This domain matters
because immutable primitives keep negotiation and middleware from sharing
surprising mutable state.

Related: `AGENTS.md`, `README.md`, `docs/ARD.md`,
`site/content/docs/build-apps/pages-navigation/`.

## Point Of View

You are the route author and middleware author who need request, response,
headers, cookies, forms, query params, and sync requests to be predictable,
typed, and independent from app/render internals.

## Protect

- **HTTP is a public stable area.** `docs/public-api.md:29-31` lists `Request`,
  `Response`, `JSONResponse`, `Redirect`, and `hx_redirect` as stable.
- **Request details are typed.** `src/chirp/http/request.py` owns htmx
  detection, URL scope, body parsing, and sync request primitives.
- **Response helpers preserve intent.** `src/chirp/http/response.py` owns
  status, headers, cookies, redirects, SSE response shape, and render intent.
- **Headers keep multi-value behavior.** `Set-Cookie` and repeated headers must
  not collapse through convenience dict conversions.
- **Forms use optional parser boundaries.** `pyproject.toml:43-45` keeps
  multipart parsing behind the `forms` extra.
- **SSE response mutation is constrained.** `docs/ARD.md:191` and
  `src/chirp/http/response.py` document no-op SSE header helpers.
- **Sync request path is performance-sensitive.** Root requires a measurement
  plan before changing `SyncRequest` or pre-encoded content behavior.
- **Validation errors are actionable.** Malformed form/header/cookie errors
  should name the field/header/config surface.

## Contract Checklist

When this domain changes, check:

- `src/chirp/http/request.py` — htmx flags, URL scope, body/form parsing,
  path/query/cookie state, sync request behavior.
- `src/chirp/http/response.py` — status/header/cookie helpers, redirect, JSON,
  SSE response, render intent, pre-encoded paths.
- `src/chirp/http/forms.py`, `headers.py`, `cookies.py` — collection semantics
  and optional dependency errors.
- `src/chirp/server/sync_handler.py` — sync request parity.
- `README.md`, `docs/public-api.md`, request/response site docs — public names
  and examples.
- `tests/test_request.py`, `tests/test_response.py`, `tests/test_headers.py`,
  `tests/test_cookies.py`, `tests/test_forms.py`, `tests/test_sync_request.py`.
- `tests/test_sync_handler.py` when sync or pre-encoded response behavior moves.

## Advocate

- **Immutable-by-default collections.** Prefer copy-on-write response helpers
  and immutable request views over hidden mutation.
- **Fast-path receipts.** Sync-path or pre-encoded changes should carry a small
  benchmark or explicit no-impact note.
- **Form parsing edge coverage.** Repeated fields, missing fields, malformed
  data, and optional dependency absence should stay tested.
- **Header diagnostics.** Bad header/cookie operations should fail with names
  users can fix.

## Do Not

- Imitate Starlette/FastAPI APIs unless they match Chirp's contract.
- Add app, router, template, or middleware dependencies here.
- Store request data in mutable globals.
- Change `SyncRequest` semantics without proof or a no-impact rationale.

## Own

**Code:** `src/chirp/http/`.
**Tests:** `tests/test_request.py`, `tests/test_response.py`,
`tests/test_headers.py`, `tests/test_cookies.py`, `tests/test_forms.py`,
`tests/test_sync_request.py`, sync handler tests.
**Docs:** request/response public docs, README return examples, forms docs.
**Agent artifacts:** this file.
**CODEOWNERS:** manual-confirmation-needed; no CODEOWNERS file exists.
