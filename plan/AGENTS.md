<!-- generated from .stewards/manifest.toml — edit the manifest, not this file -->

# Steward: plan

Keep roadmap and backlog artifacts honest about status, native GitHub hierarchy, blockers, decisions, proof, and not-now scope.

Ordinary work: use this map directly with the root map and run only affected checks.
Do not open `.stewards/PROTOCOL.md` or `.stewards/manifest.toml` unless the task is an explicit review/audit or steward-network maintenance.

## Protects

| Invariant | Sev | Backing | Proof / anchor |
| --- | --- | --- | --- |
| Active work and hierarchy remain authoritative in GitHub issues rather than duplicated roadmap checklists. | P1 | manual | plan/roadmap.md · `GitHub` |
| Every open unblocked parent reaches a ready leaf through live GitHub parent/sub-issue relationships. | P1 | none | — |

## Guardrails

- GitHub issues own active work and parent/sub-issue relationships.
- Ready is leaf-only; good-first issues remain contributor work.
- Plans never masquerade as shipped documentation.

## Edges

- prioritizes → **root** (future work)
- graduates-to → **docs** (shipped explanation)

## Owns

- **code:** `plan/`
- **tests:** `scripts/backlog.py`
- **docs:** `plan/`, `docs/rfcs/`

## Advocate

- Ranked executable leaf work with explicit proof, dependencies, dissent, blockers, and not-now scope.

## Do Not

- Duplicate issue scope in roadmap files, mark parents ready, or present speculative plans as shipped behavior.
