<!-- generated from .stewards/manifest.toml — edit the manifest, not this file -->

# Steward: i18n

Keep locale detection, catalogs, formatting, middleware, and template helpers optional and request-isolated.

Ordinary work: use this map directly with the root map and run only affected checks.
Do not open `.stewards/PROTOCOL.md` or `.stewards/manifest.toml` unless the task is an explicit review/audit or steward-network maintenance.

## Protects

| Invariant | Sev | Backing | Proof / anchor |
| --- | --- | --- | --- |
| Catalog, locale detection, middleware, formatting, and missing-key contracts retain request-scoped behavior. | P1 | machine-backed | `uv run pytest tests/test_i18n.py tests/contracts/test_i18n_keys.py -q` (`i18n-suite`) |

## Guardrails

- Current locale never lives in a mutable global.
- ICU/gettext remains deferred; richer formatting uses the documented babel-alongside pattern.

## Edges

- detects-through → **middleware** (cookies, headers, and URL)
- injects → **templating** (translation helpers)

## Owns

- **code:** `src/chirp/i18n/`
- **tests:** `tests/test_i18n.py`, `tests/contracts/test_i18n_keys.py`
- **docs:** `site/content/`
