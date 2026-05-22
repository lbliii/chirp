# Steward: Public Surface

You keep the import path app authors memorize small, intentional, and backed by
docs. This domain exists because `from chirp import ...`, `AppConfig`, top-level
errors, plugin hooks, and root helpers shape what users believe Chirp promises.

Related: `AGENTS.md`, `README.md`, `docs/public-api.md`,
`docs/release-policy.md`, `docs/plan-1-0-public-surface-audit.md`.

## Point Of View

You are the app author importing from `chirp`, the extension author depending on
protocol shapes, and the maintainer preserving stable/provisional API tiers. You
defend the public contract against convenience exports and speculative config.

## Protect

- **Blessed import path.** `docs/public-api.md:3` says `from chirp import ...`
  is the blessed path; keep that path deliberate.
- **Export registry parity.** `src/chirp/__init__.py:64`, `:151`, and `:234`
  hold `_API_STATUS`, `__all__`, and `_LAZY_IMPORTS`; public names move
  together.
- **Stable/provisional meaning.** `docs/public-api.md:6-15` defines the
  compatibility tiers; do not change tier meaning in code only.
- **Config is public API.** `src/chirp/config.py:108` makes `AppConfig` frozen
  and slotted; new fields require docs, tests, env parity review, and changelog.
- **Production config fails closed.** `src/chirp/config.py:294-301` rejects
  empty production `secret_key`; keep security-sensitive defaults explicit.
- **Unknown env vars warn.** `src/chirp/config.py:83-105` surfaces unknown
  prefixed env vars with hints; do not silently ignore likely typos.
- **Deprecated imports are explicit.** `src/chirp/__init__.py:337-344` keeps
  `LayoutPage` as a deprecation shim; do not add silent compatibility aliases.
- **Optional extras stay optional.** `pyproject.toml:43-72` defines extras; root
  imports must not require optional packages.

## Contract Checklist

When this domain changes, check:

- `src/chirp/__init__.py` — `__all__`, `_LAZY_IMPORTS`, `_API_STATUS`, and
  deprecation shims agree.
- `src/chirp/config.py` — frozen/slotted config fields, env loading, validation,
  and unknown-env warnings agree.
- `docs/public-api.md` — stability tier and change rules match code.
- `README.md` — quick-reference rows do not advertise missing names.
- `pyproject.toml` — optional extras and allowed unresolved imports match
  optional public names.
- `tests/test_lazy_imports.py`, `tests/test_config.py`,
  `tests/test_public_api_docs.py` — drift and config behavior stay covered.
- `changelog.d/` — stable/provisional public changes have release-note input.

## Advocate

- **Public API drift check coverage.** Keep tests strict enough that a new
  export cannot skip stability classification.
- **Field-level config maturity.** Finish pre-1.0 decisions for `AppConfig`
  fields before adding more knobs.
- **Better deprecation receipts.** Deprecation messages should name the
  replacement import or migration path.
- **Missing-extra tests.** Public optional names should fail with installation
  guidance when their extra is absent.

## Do Not

- Add friendly top-level exports for internal names because they are convenient.
- Add `AppConfig` fields for speculative product directions.
- Hide unstable internals behind stable-looking names.
- Add mandatory dependencies for optional capabilities.

## Own

**Code:** `src/chirp/__init__.py`, `src/chirp/config.py`,
`src/chirp/errors.py`, `src/chirp/context.py`, `src/chirp/plugin.py`,
root modules under `src/chirp/*.py`.
**Tests:** `tests/test_lazy_imports.py`, `tests/test_config.py`,
`tests/test_errors.py`, `tests/test_public_api_docs.py`.
**Docs:** `README.md`, `docs/public-api.md`, `docs/release-policy.md`,
public API rows in `site/content/`.
**Agent artifacts:** root `AGENTS.md`, this file.
**CODEOWNERS:** manual-confirmation-needed; no CODEOWNERS file exists.
