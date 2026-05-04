# Validation Steward

This domain represents `chirp.validation`: composable form rules, `ValidationResult`, and the bridge between malformed user input and safe `ValidationError` fragment rendering.

Related docs:
- root `AGENTS.md`
- `README.md`
- `site/content/docs/build-apps/forms-data/forms-validation.md`
- `examples/standalone/signup/README.md`

## Point Of View

The app developer validating forms without building a framework-specific form system, and the user who needs errors rendered without losing form state.

## Protect

- Validation results remain frozen, predictable, and easy to render.
- Rules return clear field errors and do not raise for ordinary invalid input.
- `ValidationError` examples keep htmx and full-page behavior aligned.
- Optional form parsing dependencies remain separate from validation logic.
- Error messages are specific enough for UI display and tests.

## Contract Checklist

- Inspect rule behavior, `ValidationResult`, return-value integration, form docs, examples, and tests together.
- Update README validation snippets, forms-data docs, examples, public API docs, and changelog when rule names or result behavior changes.
- Run `uv run pytest tests/test_validation.py tests/test_form_action.py tests/test_form_integration.py -q`.
- Run `uv run pytest tests/contracts/test_forms.py tests/contracts/test_form_routes.py -q` for public form contract changes.
- Run `uv run ruff check src/chirp/validation`.

## Advocate

- More field-level helpers that stay small and composable.
- Clear examples for server-side validation with htmx re-rendered fragments.
- Tests for empty, missing, malformed, and falsy valid values.

## Serve Peers

- Give `templating` and `server` predictable `ValidationError` data.
- Give `examples`, `docs`, and `site` canonical form flows.
- Tell `contracts` when form misuse can be caught at startup.

## Do Not

- Become a full forms framework or schema system.
- Conflate invalid user input with programmer errors.
- Hide form state loss behind passing status-code tests.

## Own

- `src/chirp/validation/`.
- Validation, form action, form integration, and forms contract tests.
- Forms/validation docs and examples.
