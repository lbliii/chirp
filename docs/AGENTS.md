# AGENTS.md

## Steward: Narrative Docs Steward

This domain protects design docs, RFCs, roadmap, release policy, public API notes, and explanatory
guides under `docs/`.

## Must Not Become

- A second source of truth that contradicts README, root `AGENTS.md`, or tested behavior.
- A graveyard of plans with no status.
- Marketing copy that overclaims performance, safety, or API stability.

## Documentation Ownership

This subtree owns architecture rationale, roadmap language, release policy, public API
classification, error handling, DevTools, and hypermedia footgun explanations. Mirror user-facing
changes into README and site content when needed.

## Local Checks

Start with:

- `uv run pytest tests/docs -q`
- `uv run pytest tests/test_search_index_v2.py tests/test_search_js_v2.py -q` for docs search changes
- `uv run ruff check src/chirp/docs` when docs tooling changes

## Public Contracts And Safety Boundaries

- Docs must match public behavior and tested examples.
- API stability labels are promises; do not downgrade or expand them casually.
- Performance claims need benchmark evidence and caveats.
