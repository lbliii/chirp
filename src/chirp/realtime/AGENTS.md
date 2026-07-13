<!-- generated from .stewards/manifest.toml — edit the manifest, not this file -->

# Steward: realtime

Keep post-load SSE updates reliable, correctly framed, bounded on errors, and cleaned up on disconnect.

Ordinary work: use this map directly with the root map and run only affected checks.
Do not open `.stewards/PROTOCOL.md` or `.stewards/manifest.toml` unless the task is an explicit review/audit or steward-network maintenance.

## Protects

| Invariant | Sev | Backing | Proof / anchor |
| --- | --- | --- | --- |
| SSE parsing, event formatting, streaming integration, macros, and startup contracts remain aligned. | P0 | machine-backed | `uv run pytest tests/test_sse_parser.py tests/test_sse_integration.py tests/test_sse_macros.py tests/contracts/test_sse.py -q` (`realtime-suite`) |

## Guardrails

- EventStream is post-load SSE, not initial Stream or Suspense rendering.
- One event failure does not silently kill a long-lived stream.

## Edges

- transported-by → **server** (SSE response handling)
- consumed-by → **pages** (reactive streams)

## Owns

- **code:** `src/chirp/realtime/`
- **tests:** `tests/test_sse_parser.py`, `tests/test_sse_integration.py`, `tests/contracts/test_sse.py`
- **docs:** `docs/realtime-production.md`
