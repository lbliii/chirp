<!-- generated from .stewards/manifest.toml — edit the manifest, not this file -->

# Steward: internal

Keep shared ASGI shapes, invocation plans, context propagation, kwargs resolution, and multimap protocols private and behaviorally stable.

Ordinary work: use this map directly with the root map and run only affected checks.
Do not open `.stewards/PROTOCOL.md` or `.stewards/manifest.toml` unless the task is an explicit review/audit or steward-network maintenance.

## Protects

| Invariant | Sev | Backing | Proof / anchor |
| --- | --- | --- | --- |
| Private ASGI, invocation-plan, kwargs, context, and multimap helpers retain focused behavioral coverage. | P1 | machine-backed | `uv run pytest tests/test_asgi.py tests/test_invoke_plan.py tests/test_headers.py -q` (`internal-suite`) |

## Guardrails

- Internal helpers do not become convenience public exports.
- Invocation compilation preserves sync, async, dependency, and request-context semantics.

## Edges

- hidden-behind → **public** (public call paths)
- serves → **server** (handler invocation)

## Owns

- **code:** `src/chirp/_internal/`
- **tests:** `tests/test_asgi.py`, `tests/test_invoke_plan.py`, `tests/test_headers.py`
