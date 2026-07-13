<!-- generated from .stewards/manifest.toml — edit the manifest, not this file -->

# Steward: changelog

Keep towncrier inputs small, valid, security-aware, and written in terms of user-visible impact.

Ordinary work: use this map directly with the root map and run only affected checks.
Do not open `.stewards/PROTOCOL.md` or `.stewards/manifest.toml` unless the task is an explicit review/audit or steward-network maintenance.

## Protects

| Invariant | Sev | Backing | Proof / anchor |
| --- | --- | --- | --- |
| Towncrier fragments compile into the configured release-note structure. | P1 | machine-backed | `uv run towncrier build --draft` (`changelog-draft`) |

## Guardrails

- Public API, scaffold, dependency-floor, and contract changes require fragments.
- Fragments do not begin with a Markdown list dash.

## Edges

- releases → **docs** (public behavior)

## Owns

- **code:** `changelog.d/`
- **tests:** `scripts/check_changelog_fragments.py`
- **docs:** `CHANGELOG.md`, `docs/release-policy.md`
