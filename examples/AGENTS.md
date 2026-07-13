<!-- generated from .stewards/manifest.toml — edit the manifest, not this file -->

# Steward: examples

Keep examples executable, offline-testable, dependency-complete, safe to copy, and aligned with scaffolds and public return types.

Ordinary work: use this map directly with the root map and run only affected checks.
Do not open `.stewards/PROTOCOL.md` or `.stewards/manifest.toml` unless the task is an explicit review/audit or steward-network maintenance.

## Protects

| Invariant | Sev | Backing | Proof / anchor |
| --- | --- | --- | --- |
| Examples remain executable documentation under the default offline pytest collection. | P1 | machine-backed | `uv run pytest examples -q` (`examples-suite`) |

## Guardrails

- Standalone examples do not require chirp-ui shell delegation.
- Flagship examples teach through running code and keep comments within the documented budget.
- Good-first-issue work remains reserved for external contributors.

## Edges

- mirrors → **cli** (scaffold defaults)
- demonstrates → **docs** (copyable behavior)

## Owns

- **code:** `examples/`
- **tests:** `examples/`
- **docs:** `examples/**/README.md`

## Advocate

- Offline copy-paste paths that teach return types and feed safer patterns back into scaffolds.

## Do Not

- Take good-first issues, hide optional dependencies, or commit secrets and private endpoints.
