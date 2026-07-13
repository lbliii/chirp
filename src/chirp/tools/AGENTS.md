<!-- generated from .stewards/manifest.toml — edit the manifest, not this file -->

# Steward: tools

Keep MCP tool schema, registry, handler, and events typed, deterministic, frozen with the app, and safe to expose.

Ordinary work: use this map directly with the root map and run only affected checks.
Do not open `.stewards/PROTOCOL.md` or `.stewards/manifest.toml` unless the task is an explicit review/audit or steward-network maintenance.

## Protects

| Invariant | Sev | Backing | Proof / anchor |
| --- | --- | --- | --- |
| Tool schemas, registry freeze, events, handler, client, and approvals remain typed and deterministic. | P1 | machine-backed | `uv run pytest tests/test_tools -q` (`tools-suite`) |

## Guardrails

- Schema fields trace to annotations, defaults, and docstrings.
- Protocol failures are shaped and actionable rather than vague 500s.

## Edges

- freezes-with → **app** (tool registry)
- handled-by → **server** (MCP transport)

## Owns

- **code:** `src/chirp/tools/`
- **tests:** `tests/test_tools/`
- **docs:** `README.md`
