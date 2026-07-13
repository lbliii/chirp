<!-- generated from .stewards/manifest.toml — edit the manifest, not this file -->

# Steward: cli

Keep commands, flags, diagnostics, freeze, migrations, and generated projects aligned with framework reality.

Ordinary work: use this map directly with the root map and run only affected checks.
Do not open `.stewards/PROTOCOL.md` or `.stewards/manifest.toml` unless the task is an explicit review/audit or steward-network maintenance.

## Protects

| Invariant | Sev | Backing | Proof / anchor |
| --- | --- | --- | --- |
| CLI commands, checks, resolution, and generated project defaults retain focused coverage. | P0 | machine-backed | `uv run pytest tests/cli tests/test_cli.py tests/test_cli_check.py tests/test_cli_new.py tests/test_cli_resolve.py -q` (`cli-suite`) |

## Guardrails

- Every documented flag traces to parser implementation.
- Scaffolds boot and teach current secure return-type patterns.
- Generated output changes originate in templates.

## Edges

- teaches → **examples** (scaffold patterns)
- reports → **contracts** (chirp check)

## Owns

- **code:** `src/chirp/cli/`, `src/chirp/freeze.py`
- **tests:** `tests/cli/`, `tests/test_cli.py`, `tests/test_cli_new.py`
- **docs:** `README.md`
