<!-- generated from .stewards/manifest.toml — edit the manifest, not this file -->

# Steward: docs_tooling

Keep the built-in docs plugin, autodoc, search metadata, frontmatter, and docs checks typed and reproducible.

Ordinary work: use this map directly with the root map and run only affected checks.
Do not open `.stewards/PROTOCOL.md` or `.stewards/manifest.toml` unless the task is an explicit review/audit or steward-network maintenance.

## Protects

| Invariant | Sev | Backing | Proof / anchor |
| --- | --- | --- | --- |
| Docs collection, autodoc, tools, frontmatter, links, and search formats remain deterministic and tested. | P1 | machine-backed | `uv run pytest tests/docs tests/test_search_index_v2.py tests/test_search_js_v2.py -q` (`docs-tooling`) |

## Guardrails

- Autodoc reflects registered state and docstrings rather than invented API.
- Search metadata ordering is deterministic.

## Edges

- publishes → **docs** (source-backed documentation)
- feeds → **site** (search and metadata)

## Owns

- **code:** `src/chirp/docs/`
- **tests:** `tests/docs/`, `tests/test_search_index_v2.py`
- **docs:** `site/content/docs/quality/docs-plugin/`
