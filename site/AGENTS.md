<!-- generated from .stewards/manifest.toml — edit the manifest, not this file -->

# Steward: site

Keep Bengal source content, navigation, search, assets, and release pages aligned without treating generated output as canonical source.

Ordinary work: use this map directly with the root map and run only affected checks.
Do not open `.stewards/PROTOCOL.md` or `.stewards/manifest.toml` unless the task is an explicit review/audit or steward-network maintenance.

## Protects

| Invariant | Sev | Backing | Proof / anchor |
| --- | --- | --- | --- |
| Bengal source links remain valid and generated output stays outside canonical prose. | P1 | machine-backed | `uv run pytest tests/docs/test_site_link_drift.py -q` (`site-drift`) |

## Guardrails

- site/content and config are source; site/public and site/.bengal are generated.
- Release pages agree with CHANGELOG and release policy.

## Edges

- publishes → **docs** (canonical prose)
- consumes → **docs_tooling** (search metadata)

## Owns

- **code:** `site/content/`, `site/config/`, `site/assets/`
- **tests:** `tests/docs/test_site_link_drift.py`
- **docs:** `site/content/`
