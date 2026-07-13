<!-- generated from .stewards/manifest.toml — edit the manifest, not this file -->

# Steward: server

Preserve typed return intent from handler output through ASGI, htmx negotiation, sync handling, and bytes on the wire.

Ordinary work: use this map directly with the root map and run only affected checks.
Do not open `.stewards/PROTOCOL.md` or `.stewards/manifest.toml` unless the task is an explicit review/audit or steward-network maintenance.

## Protects

| Invariant | Sev | Backing | Proof / anchor |
| --- | --- | --- | --- |
| Typed return values retain htmx, sync, streaming, SSE, response, and error negotiation semantics. | P0 | machine-backed | `uv run pytest tests/test_negotiation tests/test_response.py tests/test_sync_handler.py tests/test_sse_integration.py -q` (`server-suite`) |
| Composition responses preserve render intent and vary on HX-Request where required. | P0 | manual | src/chirp/server/negotiation.py · `HX-Request` |

## Guardrails

- Dispatch order is user-visible.
- SSE and streaming HTML stay unbuffered and distinct.
- Debug internals never leak in production.

## Edges

- executes → **templating** (render plans)
- emits → **http** (responses)

## Owns

- **code:** `src/chirp/server/`
- **tests:** `tests/test_negotiation/`, `tests/test_sync_handler.py`, `tests/test_sse_integration.py`
- **docs:** `docs/error-handling.md`, `docs/devtools.md`
