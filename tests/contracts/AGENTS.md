<!-- generated from .stewards/manifest.toml — edit the manifest, not this file -->

# Steward: contract_tests

Prove app.check() catches realistic broken routes, templates, OOB, Suspense, SSE, forms, shells, accessibility, and production safety.

Ordinary work: use this map directly with the root map and run only affected checks.
Do not open `.stewards/PROTOCOL.md` or `.stewards/manifest.toml` unless the task is an explicit review/audit or steward-network maintenance.

## Protects

| Invariant | Sev | Backing | Proof / anchor |
| --- | --- | --- | --- |
| Realistic broken apps prove issue severity, category, location, and actionable guidance through app.check(). | P0 | machine-backed | `uv run pytest tests/contracts -q` (`contract-suite`) |

## Guardrails

- Issue assertions protect category, severity, affected surface, and actionable next step.
- Fixtures model apps users could write and use TestClient or app.check().

## Edges

- proves → **contracts** (end-to-end rule behavior)

## Owns

- **code:** `tests/contracts/`
- **tests:** `tests/contracts/`
- **docs:** `docs/hypermedia-footguns.md`
