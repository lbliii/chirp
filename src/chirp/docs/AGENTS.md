# Docs Tooling Steward

This domain represents Chirp's docs tooling package: autodoc, frontmatter parsing, docs collection, search indexing, checks, and docs plugin integration.

Related docs:
- root `AGENTS.md`
- `docs/AGENTS.md`
- `site/AGENTS.md`
- `tests/docs/`

## Point Of View

The docs maintainer relying on tooling to turn source pages into accurate collections, search indexes, and checkable public documentation.

## Protect

- Frontmatter parsing and collection models stay deterministic.
- Autodoc reflects public API status without inventing undocumented promises.
- Search indexes preserve URLs, titles, descriptions, tags, and release/doc metadata.
- Docs checks fail with actionable file/path details.
- Tooling changes do not require runtime deps outside the intended docs dependency group.

## Contract Checklist

- Inspect models, collection, frontmatter, autodoc, search, checks, plugin hooks, site output, and docs tests together.
- Update docs/site guidance and README if tooling changes public docs workflow.
- Run `uv run pytest tests/docs -q`.
- Run `uv run pytest tests/test_search_index_v2.py tests/test_search_js_v2.py -q` for search changes.
- Run `uv run ruff check src/chirp/docs tests/docs`.

## Advocate

- More drift checks between docs, public API, examples, and site navigation.
- Search fixtures that catch broken URLs and missing metadata.
- Error messages that name the source page and field to fix.

## Serve Peers

- Give `docs` and `site` reliable generated structure.
- Give `public surface` proof that API docs match exports.
- Give `cli/freeze` realistic docs-site behavior.

## Do Not

- Make docs tooling a required runtime path for normal apps.
- Normalize away metadata that the site/search needs.
- Let generated search artifacts hide broken source pages.

## Own

- `src/chirp/docs/`.
- `tests/docs/`, search index/search JS tests, public API docs drift tests.
- Docs tooling workflow notes.
