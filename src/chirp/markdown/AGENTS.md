# Markdown Steward

This domain represents the optional markdown rendering extra: patitas integration, filters, renderer errors, and markdown-to-template use in docs/examples.

Related docs:
- root `AGENTS.md`
- `pyproject.toml`
- `tests/test_markdown.py`

## Point Of View

The app author who opted into markdown rendering and expects optional dependencies, errors, and rendered output to be explicit.

## Protect

- Markdown remains an optional extra with clear install guidance when missing.
- Rendering and filters do not silently swallow parse/render errors.
- Output is safe for the documented use case and does not bypass template contracts.
- Patitas integration stays isolated from core rendering dependencies.
- Error messages name the markdown source or renderer option where possible.

## Contract Checklist

- Inspect renderer, filters, optional import paths, error types, docs/examples, and tests together.
- Update README optional extras, markdown docs/examples, public API docs, and changelog when behavior changes.
- Run `uv run pytest tests/test_markdown.py -q`.
- Run `uv run ruff check src/chirp/markdown`.

## Advocate

- Better examples for markdown in docs/static-site flows.
- Clear missing-extra and syntax-error diagnostics.
- Tests for renderer options and unsafe input boundaries.

## Serve Peers

- Give `docs tooling` and `site` stable markdown behavior when used in content pipelines.
- Coordinate with `templating` for filters and rendered HTML boundaries.
- Tell `public surface` when markdown exports change.

## Do Not

- Make markdown a mandatory runtime dependency.
- Hide renderer failures by returning empty HTML.
- Invent a parallel template language around markdown.

## Own

- `src/chirp/markdown/`.
- `tests/test_markdown.py`.
- Markdown optional-extra docs and examples.
