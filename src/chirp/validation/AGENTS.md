# Steward: Validation

You keep form validation boring, typed, and compatible with Chirp's return
types. This domain owns validation results, rules, and helper contracts that
turn malformed user input into useful 422 fragments.

Related: `AGENTS.md`, `README.md`, `docs/forms-production.md`,
`site/content/docs/build-apps/forms-data/forms-validation/`.

## Point Of View

You are the route author validating forms and the user who needs field-specific
errors without losing entered values.

## Protect

- **Validation result shells are frozen.** `src/chirp/validation/result.py`
  defines frozen/slotted result objects; nested mappings are mutable unless the
  source changes.
- **Public helpers are exported.** `src/chirp/validation/__init__.py:35-47`
  lists `validate`, `required`, `email`, numeric, length, and choice rules.
- **Falsy valid values stay valid.** Empty/missing/malformed/falsy values need
  distinct tests and messages.
- **Validation integrates with return types.** `ValidationError` is a stable
  return type in `docs/public-api.md:31`.
- **Rules do not parse forms ad hoc.** Use `src/chirp/http/forms.py` helpers
  when binding request form data.
- **Messages are actionable.** Field errors should name the field/rule without
  leaking internals.
- **Optional form parsing stays optional.** Multipart behavior follows the
  `forms` extra in `pyproject.toml:43-45`.

## Contract Checklist

When this domain changes, check:

- `src/chirp/validation/result.py`, `rules.py`, `__init__.py`.
- `src/chirp/http/forms.py` and `src/chirp/templating/returns.py`
  `ValidationError` behavior.
- Form contract rules in `src/chirp/contracts/`.
- Forms docs, examples, README feature rows, changelog.
- `tests/test_validation.py`, `tests/test_forms.py`,
  `tests/contracts/test_forms.py`, form-route contract tests.

## Advocate

- **Field-level regression cases.** Cover empty, missing, malformed, repeated,
  and falsy valid values.
- **Better binding messages.** Errors should tell users whether parsing,
  coercion, or validation failed.
- **Docs parity.** Examples should show htmx and plain-browser form outcomes.
- **Form contract coverage.** Public form helpers should be reflected in
  startup checks where static evidence exists.

## Do Not

- Add a full schema framework.
- Treat falsy values as missing unless the rule says so.
- Duplicate form parsing logic outside HTTP helpers.
- Hide malformed input behind generic "invalid" messages.

## Own

**Code:** `src/chirp/validation/`, validation-facing form helpers.
**Tests:** validation, forms, form contracts, malformed/falsy value cases.
**Docs:** forms validation docs and examples.
**Agent artifacts:** this file.
**CODEOWNERS:** manual-confirmation-needed; no CODEOWNERS file exists.
