<!-- generated from .stewards/manifest.toml — edit the manifest, not this file -->

# Steward: public

Keep the import path app authors memorize small, intentional, lazy, and documented.

Ordinary work: use this map directly with the root map and run only affected checks.
Do not open `.stewards/PROTOCOL.md` or `.stewards/manifest.toml` unless the task is an explicit review/audit or steward-network maintenance.

## Protects

| Invariant | Sev | Backing | Proof / anchor |
| --- | --- | --- | --- |
| Every exported public name is lazy-importable and has one documented maturity classification. | P0 | machine-backed | `uv run pytest tests/test_lazy_imports.py tests/test_public_api_docs.py -q` (`public-contract`) |
| AppConfig validation, environment loading, unknown-variable warnings, and production safety remain covered. | P0 | machine-backed | `uv run pytest tests/test_config.py -q` (`config-contract`) |
| Top-level public exports move together across __all__, _LAZY_IMPORTS, and _API_STATUS. | P1 | manual | src/chirp/__init__.py · `_LAZY_IMPORTS` |

## Guardrails

- New top-level names move together across __all__, _LAZY_IMPORTS, _API_STATUS, public docs, tests, and changelog.
- AppConfig remains frozen and slotted; new fields are public API and require environment-parity review.

## Edges

- explained-by → **docs** (public API and release policy)

## Owns

- **code:** `src/chirp/*.py`
- **tests:** `tests/test_lazy_imports.py`, `tests/test_config.py`, `tests/test_public_api_docs.py`
- **docs:** `README.md`, `docs/public-api.md`, `docs/release-policy.md`

## Advocate

- Strict drift checks for exports, maturity tiers, config fields, and optional missing-extra behavior.

## Do Not

- Add convenience exports, speculative AppConfig fields, or mandatory dependencies for optional capabilities.
