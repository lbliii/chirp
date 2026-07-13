<!-- generated from .stewards/manifest.toml — edit the manifest, not this file -->

# Steward: docs

Preserve source-backed architecture, public API, deployment, release, RFC, and migration explanations without presenting plans as shipped behavior.

Ordinary work: use this map directly with the root map and run only affected checks.
Do not open `.stewards/PROTOCOL.md` or `.stewards/manifest.toml` unless the task is an explicit review/audit or steward-network maintenance.

## Protects

| Invariant | Sev | Backing | Proof / anchor |
| --- | --- | --- | --- |
| Public API and published site links remain synchronized with current source. | P1 | machine-backed | `uv run pytest tests/test_public_api_docs.py tests/docs/test_site_link_drift.py -q` (`docs-drift`) |

## Guardrails

- Every public flag, field, name, and compatibility claim traces to code or focused proof.
- Performance, security, and production claims carry evidence and caveats.

## Edges

- published-by → **site** (Bengal content)
- released-by → **changelog** (user-visible changes)

## Owns

- **code:** `docs/`
- **tests:** `tests/test_public_api_docs.py`, `tests/docs/`
- **docs:** `docs/`, `README.md`
