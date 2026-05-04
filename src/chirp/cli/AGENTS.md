# CLI And Scaffold Steward

This domain represents `chirp` commands: `new`, `run`, `check`, `routes`, `freeze`, migration/security checks, template scaffolds, and import-string resolution.

Related docs:
- root `AGENTS.md`
- `README.md`
- `docs/release-policy.md`
- `tests/cli/`

## Point Of View

The developer at a terminal and the future app author learning Chirp patterns from generated files.

## Protect

- CLI commands reflect `App` behavior instead of creating a separate runtime.
- Scaffolded apps teach patterns `app.check()` accepts.
- Errors name the import string, template, block, route, or config flag to fix.
- `chirp check` output remains stable and actionable enough for CI.
- `chirp freeze` preserves static output contracts and docs-site needs.

## Contract Checklist

- Inspect command flags/output, import resolution, generated templates, scaffolds, freeze behavior, security checks, docs, examples, and changelog together.
- Update README command tables, scaffold docs, examples, site docs, and release notes when flags, generated files, or output changes.
- Run `uv run pytest tests/cli tests/test_cli.py tests/test_cli_check.py tests/test_cli_run.py -q`.
- Run `uv run pytest tests/test_cli_new.py tests/test_cli_resolve.py tests/cli/test_scaffold_contracts.py -q`.
- Run `uv run ruff check src/chirp/cli`.

## Advocate

- Short, precise terminal errors with next actions.
- Scaffolds that exercise route directory, htmx, SSE, CSRF, and Alpine CDN safety correctly.
- CI-friendly command output for checks and routes.

## Serve Peers

- Give `app`, `server`, and `contracts` user-facing command paths.
- Give `examples`, `docs`, and `site` generated patterns that match current guidance.
- Tell `tests` when command shape or scaffold expectations change.

## Do Not

- Diverge command behavior from programmatic `App` behavior.
- Generate unsafe htmx inheritance, broad targets, missing CSRF, or bare Alpine CDN URLs.
- Print vague failures that require reading source.

## Own

- `src/chirp/cli/`.
- CLI, scaffold, resolve, run, check, freeze, route, and security-check tests.
- README command tables, scaffold docs, and generated template fixtures.
