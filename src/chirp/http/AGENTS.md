<!-- generated from .stewards/manifest.toml — edit the manifest, not this file -->

# Steward: http

Keep request, response, headers, cookies, forms, query, and sync primitives typed and predictable.

Ordinary work: use this map directly with the root map and run only affected checks.
Do not open `.stewards/PROTOCOL.md` or `.stewards/manifest.toml` unless the task is an explicit review/audit or steward-network maintenance.

## Protects

| Invariant | Sev | Backing | Proof / anchor |
| --- | --- | --- | --- |
| Request, response, header, cookie, form, and sync primitives preserve public behavior. | P0 | machine-backed | `uv run pytest tests/test_request.py tests/test_response.py tests/test_headers.py tests/test_cookies.py tests/test_forms.py tests/test_sync_request.py -q` (`http-suite`) |

## Guardrails

- Repeated headers such as Set-Cookie never collapse through convenience mappings.
- Multipart parsing remains behind the forms extra.

## Edges

- transported-by → **server** (negotiation and sender)

## Owns

- **code:** `src/chirp/http/`
- **tests:** `tests/test_request.py`, `tests/test_response.py`, `tests/test_forms.py`
- **docs:** `docs/public-api.md`
