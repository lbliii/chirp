# AGENTS.md

## Steward: CLI And Scaffold Steward

This domain protects `chirp` commands: `new`, `run`, `check`, `routes`, `freeze`, security checks,
template scaffolds, and import-string resolution.

## Must Not Become

- A separate runtime with behavior that differs from `App`.
- A scaffold generator that teaches patterns contracts would reject.
- A CLI that prints vague errors when a route/template/block/config is wrong.

## Documentation Ownership

Update README command tables, scaffold docs, examples, and release notes when CLI flags, generated
files, or command output changes.

## Local Checks

Start with:

- `uv run pytest tests/cli tests/test_cli.py tests/test_cli_check.py tests/test_cli_run.py -q`
- `uv run pytest tests/test_cli_new.py tests/test_cli_resolve.py tests/cli/test_scaffold_contracts.py -q`
- `uv run ruff check src/chirp/cli`

## Public Contracts And Safety Boundaries

- Generated apps are documentation. They must use safe return types, `sse_scope`, CSRF patterns, and
  explicit Alpine CDN URLs where relevant.
- CLI errors should tell the reader the import string, template, block, or config flag to fix.
- `chirp check` output shape is part of developer experience; keep it stable and actionable.
