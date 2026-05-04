# Public Surface Steward

This domain represents Chirp's top-level developer contract: `chirp.__all__`, lazy imports, `AppConfig`, top-level errors, plugins, request context, shell helpers, and root modules that shape what app authors think Chirp is.

Related docs:
- root `AGENTS.md`
- `README.md`
- `docs/public-api.md`
- `docs/release-policy.md`

## Point Of View

The app author importing `from chirp import ...`, the plugin author relying on protocol shapes, and the maintainer promising stable/provisional API tiers.

## Protect

- `from chirp import ...` remains the blessed import path.
- Top-level exports are intentional, classified, tested, and documented.
- `AppConfig` stays frozen/slotted and does not grow speculative fields.
- Public errors stay actionable and stable enough for user handling.
- Root modules do not bypass return types, Kida rendering, or contract checks.

## Contract Checklist

- Update `__all__`, `_LAZY_IMPORTS`, `_API_STATUS`, and lazy import tests for any top-level name.
- Update `docs/public-api.md`, README quick-reference tables, and changelog fragments for stable/provisional API changes.
- Run `uv run pytest tests/test_lazy_imports.py tests/test_config.py tests/test_errors.py tests/test_public_api_docs.py -q`.
- Run `uv run ty check src/chirp/` and `uv run ruff check src/chirp/__init__.py src/chirp/config.py src/chirp/errors.py`.
- Add migration notes when stable behavior changes.

## Advocate

- Smaller public surface with clearer tiers.
- Better error messages that name replacement APIs and migration paths.
- Contract tests that keep public docs and exports in sync.

## Serve Peers

- Tell `cli`, `docs`, `site`, and `examples` when public names or config defaults change.
- Tell `contracts` and `testing` when a new public shape needs startup checks or helper coverage.
- Tell optional-extra stewards when import errors need clearer install guidance.

## Do Not

- Add convenience exports just because an internal name is useful.
- Hide unstable internals behind friendly names.
- Introduce parallel response or serialization APIs.
- Add new mandatory dependencies without a design check-in.

## Own

- `src/chirp/__init__.py`, `src/chirp/config.py`, `src/chirp/errors.py`, `src/chirp/context.py`, `src/chirp/plugin.py`.
- `tests/test_lazy_imports.py`, `tests/test_config.py`, `tests/test_errors.py`, `tests/test_public_api_docs.py`.
- `docs/public-api.md`, README public tables, changelog fragments for API changes.
