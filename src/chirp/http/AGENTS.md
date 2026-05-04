# HTTP Primitives Steward

This domain represents Chirp's immutable HTTP vocabulary: `Request`, `Response`, `JSONResponse`, cookies, forms, headers, query params, and `SyncRequest`.

Related docs:
- root `AGENTS.md`
- `README.md`
- `site/content/docs/build-apps/pages-navigation/request-response.md`
- `site/content/docs/about/thread-safety.md`

## Point Of View

The route author and middleware author who need request/response objects to be predictable, typed, immutable where possible, and independent from template/app internals.

## Protect

- HTTP collections are immutable or copy-on-write.
- Header behavior preserves multi-value semantics, especially `Set-Cookie`.
- Response transformations return new values or remain thread-safe.
- Form/query/cookie parsing is deterministic and boundary-validated.
- `SyncRequest` and pre-encoded responses stay performance-sensitive.

## Contract Checklist

- Check request construction, response helpers, headers/cookies/forms/query behavior, and sync handling together.
- Update README return-value examples, `docs/public-api.md`, request/response docs, and error docs for behavior changes.
- Run `uv run pytest tests/test_request.py tests/test_response.py tests/test_headers.py -q`.
- Run `uv run pytest tests/test_cookies.py tests/test_forms.py tests/test_sync_request.py -q`.
- Run `uv run pytest tests/test_sync_handler.py -q` when sync request behavior changes.

## Advocate

- Clearer error messages for malformed forms, invalid headers, and sync-only constraints.
- Narrower immutable types instead of defensive validation inside internals.
- Benchmarked fast-path improvements with documented tradeoffs.

## Serve Peers

- Give `server` stable primitives for ASGI translation and negotiation.
- Give `middleware` safe request/response mutation patterns.
- Give `testing` helpers the same behavior users hit through real requests.

## Do Not

- Imitate Starlette/FastAPI APIs unless they match Chirp's contract.
- Add template, app, router, or middleware dependencies here.
- Store mutable request data globally.
- Change sync fast-path behavior without proof or explicit no-impact rationale.

## Own

- `src/chirp/http/`.
- `tests/test_request.py`, `tests/test_response.py`, `tests/test_headers.py`, `tests/test_cookies.py`, `tests/test_forms.py`, `tests/test_sync_request.py`.
- Request/response public docs and examples.
