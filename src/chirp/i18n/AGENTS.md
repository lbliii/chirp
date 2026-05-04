# i18n Steward

This domain represents Chirp's internationalization helpers: catalogs, locale detection, formatting, and i18n middleware.

Related docs:
- root `AGENTS.md`
- `tests/test_i18n.py`
- `docs/rfcs/004-url-for.md`

## Point Of View

The app author localizing a Chirp app and the user who expects locale detection and formatting to be consistent across requests.

## Protect

- Locale detection is deterministic and request-scoped.
- Catalog lookups and formatting do not leak state across apps or threads.
- Middleware behavior is explicit about where locale comes from.
- URL generation and locale prefixes do not become implicit magic.
- Missing translations fail or fall back according to documented behavior.

## Contract Checklist

- Inspect catalog loading, detection, formatting, middleware, request context, docs/examples, and tests together.
- Update public API docs, locale-related route docs/RFCs, examples, and changelog when behavior changes.
- Run `uv run pytest tests/test_i18n.py tests/test_context.py -q`.
- Run `uv run ruff check src/chirp/i18n`.

## Advocate

- Clearer locale detection precedence docs.
- Tests for concurrent requests with different locales.
- Explicit integration examples with routing and templates.

## Serve Peers

- Give `middleware` request-scoped locale behavior.
- Give `templating` stable formatting/filter inputs.
- Tell `routing` and `docs` when locale affects URL guidance.

## Do Not

- Store current locale in mutable module globals.
- Add hidden URL-prefix behavior outside routing/app contracts.
- Treat missing translations as silent data loss.

## Own

- `src/chirp/i18n/`.
- i18n and context isolation tests.
- Locale-related docs and examples.
