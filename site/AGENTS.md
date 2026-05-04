# Docs Site Steward

This domain represents the Bengal-powered published documentation site: `site/content`, `site/config`, search config, release notes, and generated public artifacts.

Related docs:
- root `AGENTS.md`
- `site/content/docs/about/architecture.md`
- `docs/release-policy.md`
- `README.md`

## Point Of View

The user reading published docs and the release operator trusting static output, navigation, search, and release pages.

## Protect

- Published navigation matches the current docs IA and does not break links.
- Site content does not drift from README, `docs/`, examples, or tested behavior.
- Search and release metadata stay accurate and user-facing.
- Static output preserves relative URLs, release readability, and generated artifact expectations.
- `site/public` churn is intentional, not incidental.

## Contract Checklist

- Inspect content pages, config, search metadata, release pages, link references, source docs/README/examples, and generated output together.
- Update source docs or README when site content changes the source of truth.
- Run `uv run pytest tests/docs -q`.
- Run `uv run pytest tests/test_freeze_site.py tests/test_search_index_v2.py tests/docs/test_site_link_drift.py -q`.
- Run the Bengal/site build command used by the repo when changing site config or generated content.

## Advocate

- Navigation organized around user jobs, not internal package names.
- Link drift tests for every doc move.
- Release pages that explain migration impact, not just version numbers.

## Serve Peers

- Give `docs` feedback when source material does not fit published IA.
- Give `examples` and package stewards accurate links to canonical guides.
- Give `cli/freeze` realistic static-site requirements.

## Do Not

- Fork docs manually from README or `docs/` without noting source-of-truth movement.
- Commit generated `site/public` churn unless the task explicitly updates published output.
- Hide broken links or stale search entries.

## Own

- `site/content/`, `site/config/`, release pages, search config, and intentional generated artifacts.
- Docs link drift, freeze site, search index, and site content tests.
