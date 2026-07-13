<!-- generated from .stewards/manifest.toml — edit the manifest, not this file -->

# Steward: validation

Keep form validation typed, unsurprising, and capable of returning useful 422 fragments without losing input.

Ordinary work: use this map directly with the root map and run only affected checks.
Do not open `.stewards/PROTOCOL.md` or `.stewards/manifest.toml` unless the task is an explicit review/audit or steward-network maintenance.

## Protects

| Invariant | Sev | Backing | Proof / anchor |
| --- | --- | --- | --- |
| Validation and form behavior distinguish missing, malformed, repeated, empty, and valid falsy values. | P1 | machine-backed | `uv run pytest tests/test_validation.py tests/test_forms.py tests/contracts/test_forms.py -q` (`validation-suite`) |

## Guardrails

- Falsy valid values are not treated as missing.
- Rules reuse HTTP form binding rather than parsing requests independently.

## Edges

- binds → **http** (form data)
- returns → **templating** (ValidationError)

## Owns

- **code:** `src/chirp/validation/`
- **tests:** `tests/test_validation.py`, `tests/test_forms.py`, `tests/contracts/test_forms.py`
- **docs:** `docs/forms-production.md`
