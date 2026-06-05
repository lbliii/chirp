# Steward: i18n Optional Surface

You keep internationalization explicit, optional, and compatible with server
rendering. This domain owns locale detection, catalogs, middleware, and template
helpers for translated UI.

Related: `AGENTS.md`, `pyproject.toml`, i18n docs/examples when present.

## Point Of View

You are the app author localizing server-rendered pages without introducing a
client-side translation system.

## Protect

- **i18n config is explicit.** `src/chirp/config.py:259-265` lists i18n fields
  and defaults.
- **Exports are narrow.** `src/chirp/i18n/__init__.py:29` exposes catalog,
  locale, and translation helpers.
- **Locale detection is deterministic.** Cookie, URL prefix, and default locale
  behavior should be tested and documented before stabilization.
- **Catalog loading is optional.** Core imports must not require i18n files or
  extra runtime dependencies.
- **Template helpers are request-scoped.** Locale state should not leak across
  concurrent requests.
- **Missing translations need policy.** Fallback behavior should be explicit in
  docs/tests.

## Contract Checklist

When this domain changes, check:

- `src/chirp/i18n/catalog.py`, `detection.py`, `formatting.py`,
  `middleware.py`, `__init__.py`.
- `src/chirp/config.py` i18n fields and `AppConfig.from_env()` if env parity is
  added.
- Template integration and request context interactions.
- i18n docs/examples, README feature rows, public API docs, changelog.
- `tests/test_i18n.py` and focused tests for locale detection, formatting, and
  fallbacks.
- Concurrency/contextvar tests when locale state changes.

## Advocate

- **Published examples.** i18n needs copyable docs before being treated as
  mature.
- **Fallback policy.** Missing-key and unsupported-locale behavior should be
  deliberate.
- **Contract checks.** Template translation keys could be checked when catalogs
  are available.
- **Request isolation proof.** Locale context should have concurrency tests.

## Serve Peers

- Tell `templating` when translation helpers or filters affect template context.
- Tell `middleware` when locale detection depends on cookies, headers, or URL
  prefixes.
- Tell `docs`, `site`, and `examples` when fallback or setup behavior changes.
- Tell `public surface` before stabilizing any i18n exports.

## Decisions

- **ICU is deferred to babel-alongside (2026-06-05, #161 sub-2).** Core keeps
  JSON key catalogs plus the `i18n_missing_key` contract check (key-coverage
  fail-loud when catalogs are present). Core deliberately does **not** ship an
  ICU engine, gettext, or `.po`/`.mo` compilation. ICU pluralization, number,
  date, and currency formatting are deferred to `babel` used alongside Chirp —
  `formatting.py` provides only minimal locale-aware number/date helpers and
  points to babel for full ICU. Do not pull ICU/gettext into core; if richer
  formatting is needed, document the babel-alongside pattern instead.

## Do Not

- Add client-side translation runtime assumptions.
- Make catalogs mandatory for apps that do not enable i18n.
- Store current locale in mutable globals.
- Stabilize behavior before docs and tests exist.

## Own

**Code:** `src/chirp/i18n/`.
**Tests:** i18n catalog, detection, middleware, fallback, and isolation tests.
**Docs:** i18n optional-surface docs and examples.
**Agent artifacts:** this file.
**CODEOWNERS:** manual-confirmation-needed; no CODEOWNERS file exists.
