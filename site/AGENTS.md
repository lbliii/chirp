# AGENTS.md

## Steward: Docs Site Steward

This domain protects the Bengal-powered published documentation site: `site/content`,
`site/config`, search config, release notes, and generated public artifacts.

## Must Not Become

- A manual fork of docs that diverges from README and `docs/`.
- A checked-in generated-output churn zone for unrelated changes.
- A site that hides broken links, stale search entries, or missing release context.

## Documentation Ownership

Site content owns published navigation, release pages, docs taxonomy, search settings, and build
configuration. Coordinate source-of-truth changes with `docs/` and README.

## Local Checks

Start with:

- `uv run pytest tests/docs -q`
- `uv run pytest tests/test_freeze_site.py tests/test_search_index_v2.py -q`
- Run the Bengal/site build command used by the repo only when changing site config or generated content.

## Public Contracts And Safety Boundaries

- Avoid committing generated `site/public` churn unless the task explicitly updates published output.
- Search and release metadata are user-facing contracts.
- Static output must preserve links, relative URLs, and release note readability.
