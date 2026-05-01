# AGENTS.md

## Steward: Public Surface Steward

This domain protects Chirp's top-level developer contract: `chirp.__all__`, lazy imports,
`AppConfig`, top-level errors, plugins, request context, shell helpers, and other root modules that
shape what app authors think Chirp is.

## Must Not Become

- A dumping ground for convenience exports.
- A parallel framework surface that bypasses return types, contracts, or Kida rendering.
- A place to hide unstable internals behind friendly names.

## Documentation Ownership

Update `docs/public-api.md`, README quick-reference tables, and changelog fragments when stable or
provisional exports change. Public API changes need migration notes if behavior changes.

## Local Checks

Start with:

- `uv run pytest tests/test_lazy_imports.py tests/test_config.py tests/test_errors.py -q`
- `uv run ty check src/chirp/`
- `uv run ruff check src/chirp/__init__.py src/chirp/config.py src/chirp/errors.py`

## Public Contracts And Safety Boundaries

- `from chirp import ...` is the blessed import path.
- Adding a top-level name requires `__all__`, `_LAZY_IMPORTS`, `_API_STATUS`, tests, and docs.
- New return types, config fields, mandatory deps, or protocol shapes need a design check-in first.
- Keep root dataclasses frozen/slotted unless mutability is explicit and locked.
