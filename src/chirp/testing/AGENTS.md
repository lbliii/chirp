<!-- generated from .stewards/manifest.toml — edit the manifest, not this file -->

# Steward: testing

Keep public TestClient and assertion helpers faithful to real routing, negotiation, middleware, rendering, and SSE behavior.

Ordinary work: use this map directly with the root map and run only affected checks.
Do not open `.stewards/PROTOCOL.md` or `.stewards/manifest.toml` unless the task is an explicit review/audit or steward-network maintenance.

## Protects

| Invariant | Sev | Backing | Proof / anchor |
| --- | --- | --- | --- |
| Public test helpers exercise realistic negotiation, fragments, SSE wiring, and response intent. | P1 | machine-backed | `uv run pytest tests/test_testing_helpers.py tests/test_sse_testing.py -q` (`testing-suite`) |

## Guardrails

- Fragment assertions reject full documents.
- Helpers use public app paths unless their names explicitly promise a lower-level shortcut.

## Edges

- used-by → **tests** (public regression proof)
- exercises → **server** (real negotiation)

## Owns

- **code:** `src/chirp/testing/`
- **tests:** `tests/test_testing_helpers.py`, `tests/test_sse_testing.py`
- **docs:** `site/content/docs/quality/testing/`
