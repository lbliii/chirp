<!-- generated from .stewards/manifest.toml — edit the manifest, not this file -->

# Steward: tests

Keep tests as executable bug reports through public paths, with deterministic offline and free-threaded proof.

Ordinary work: use this map directly with the root map and run only affected checks.
Do not open `.stewards/PROTOCOL.md` or `.stewards/manifest.toml` unless the task is an explicit review/audit or steward-network maintenance.

## Protects

| Invariant | Sev | Backing | Proof / anchor |
| --- | --- | --- | --- |
| Chirp's framework tests retain a single exact full-suite entrypoint. | P1 | machine-backed | `uv run pytest tests -q` (`full-tests`) |

## Guardrails

- Escaped bugs gain named regression tests.
- Network-dependent tests are isolated and explicitly marked.
- Coverage remains at least 80 percent for code changes.

## Edges

- verifies → **root** (repository behavior)
- uses → **testing** (public helpers)

## Owns

- **code:** `tests/`
- **tests:** `tests/`
- **docs:** `docs/plan-contract-tests-reliability.md`
