<!-- generated from .stewards/manifest.toml — edit the manifest, not this file -->

# Steward: ext

Keep optional extension adapters useful without making chirp-ui or another integration redefine core Chirp.

Ordinary work: use this map directly with the root map and run only affected checks.
Do not open `.stewards/PROTOCOL.md` or `.stewards/manifest.toml` unless the task is an explicit review/audit or steward-network maintenance.

## Protects

| Invariant | Sev | Backing | Proof / anchor |
| --- | --- | --- | --- |
| chirp-ui remains an optional, versioned bridge with tested runtime and import boundaries. | P0 | machine-backed | `uv run pytest tests/test_chirpui_boundary.py tests/test_chirpui_compat_ci.py tests/test_chirpui_scaffold_default.py -q` (`extension-suite`) |

## Guardrails

- Extension imports remain lazy or guarded.
- The UI extra and generated scaffold currently require chirp-ui>=0.11.2; future floor changes need changelog and scaffold/example proof.
- use_chirp_ui owns its Alpine and nonce-CSP wiring; changing it is a security-default change.

## Edges

- exported-by → **public** (optional bridge)
- changes → **security** (CSP defaults)

## Owns

- **code:** `src/chirp/ext/`
- **tests:** `tests/test_chirpui_boundary.py`, `tests/test_chirpui_compat_ci.py`, `tests/test_chirpui_scaffold_default.py`
- **docs:** `docs/rfcs/001-component-filter-contract.md`
