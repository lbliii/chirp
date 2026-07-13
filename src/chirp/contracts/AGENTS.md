<!-- generated from .stewards/manifest.toml — edit the manifest, not this file -->

# Steward: contracts

Make broken hypermedia, route, security, form, and extension wiring fail at startup through actionable app.check() issues.

Ordinary work: use this map directly with the root map and run only affected checks.
Do not open `.stewards/PROTOCOL.md` or `.stewards/manifest.toml` unless the task is an explicit review/audit or steward-network maintenance.

## Protects

| Invariant | Sev | Backing | Proof / anchor |
| --- | --- | --- | --- |
| Contract rules retain real-app coverage across routes, templates, OOB, Suspense, SSE, forms, security, and extensions. | P0 | machine-backed | `uv run pytest tests/contracts -q` (`contract-suite`) |
| Contract severities, issues, coverage, and results remain typed public behavior. | P1 | manual | src/chirp/contracts/types.py · `class Severity` |

## Guardrails

- Severity, category, coverage, message, and location are product behavior.
- Checks use stable frozen snapshots and the HypermediaProgram rather than rescanning independent truth.

## Edges

- proved-by → **contract_tests** (real broken-app fixtures)
- consumes → **app** (contract snapshots)

## Owns

- **code:** `src/chirp/contracts/`
- **tests:** `tests/contracts/`
- **docs:** `docs/hypermedia-footguns.md`, `site/content/docs/quality/contracts-debugging/`

## Advocate

- Checks that prevent visible corruption and tell developers exactly what to fix.

## Do Not

- Become a preference linter, emit warnings users learn to ignore, or silently change severity.
