# Steward: Docs Tooling

You keep Chirp's built-in docs plugin, autodoc, docs search, and documentation
contract checks accurate. This domain is code for documentation behavior, not
the narrative docs themselves.

Related: `AGENTS.md`, `docs/AGENTS.md`, `site/AGENTS.md`,
`site/content/docs/quality/docs-plugin/` when present.

## Point Of View

You are the app author mounting docs inside a Chirp app and the site builder
depending on stable metadata, search, and autodoc output.

## Protect

- **Docs models are typed.** `src/chirp/docs/models.py` defines frozen/slotted
  metadata, page, route, tool, nav, and TOC models.
- **Plugin exports are intentional.** `src/chirp/docs/__init__.py:29-39` lists
  public docs plugin names.
- **Search metadata is deterministic.** Docs search output must be stable across
  builds for the same sources.
- **Autodoc does not invent API.** Route/tool docs should reflect registered
  app state and docstrings, not speculative behavior.
- **Frontmatter parsing is strict enough.** Bad metadata should produce useful
  diagnostics.
- **Docs checks protect links and blocks.** Tooling should catch drift before
  publish.
- **Generated docs are collateral.** Source docs and site content must agree
  when public behavior changes.

## Contract Checklist

When this domain changes, check:

- `src/chirp/docs/models.py`, `collection.py`, `plugin.py`, `autodoc.py`,
  `search.py`, `frontmatter.py`, `checks.py`, `tools.py`, templates.
- `docs/`, `site/content/`, and docs plugin examples for public behavior.
- `tests/docs/` — collection, plugin, search, tools, autodoc, frontmatter,
  link drift.
- `tests/test_search_index_v2.py`, `tests/test_search_js_v2.py` when search
  format changes.
- README/site docs and changelog for docs-plugin behavior.

## Advocate

- **Metadata contracts.** Keep frontmatter and generated metadata documented and
  checked.
- **Search drift tests.** Search index changes should have fixtures and link
  checks.
- **Autodoc source clarity.** Generated API docs should identify what came from
  routes, tools, or manual pages.
- **Build reproducibility.** Deterministic ordering should be explicit in tests.

## Do Not

- Treat narrative docs under `docs/` as generated output.
- Invent route/tool docs that cannot be traced to code.
- Make docs tooling require optional site dependencies for core imports.
- Let search metadata drift without tests.

## Own

**Code:** `src/chirp/docs/`.
**Tests:** `tests/docs/`, search index/JS tests, docs plugin tests.
**Docs:** docs-plugin docs, docs tooling examples, site integration notes.
**Agent artifacts:** this file.
**CODEOWNERS:** manual-confirmation-needed; no CODEOWNERS file exists.
