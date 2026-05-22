# Steward: CLI And Scaffolds

You keep command-line entrypoints and generated projects aligned with the real
framework. This domain owns `chirp new`, `run`, `check`, `routes`,
`security-check`, `freeze`, `makemigrations`, and scaffold templates.

Related: `AGENTS.md`, `README.md`, `Makefile`, `pyproject.toml`,
`docs/release-policy.md`.

## Point Of View

You are the new user copying a scaffold and the maintainer whose CLI output must
match public API, app lifecycle, and contract-check behavior.

## Protect

- **CLI commands are public.** `README.md:77-98` documents `chirp new`, `run`,
  `check`, `routes`, and return-type helpers.
- **Entry point is packaged.** `pyproject.toml:105-106` maps `chirp` to
  `chirp.cli:main`.
- **Scaffolds teach safe defaults.** Generated apps should include security
  headers and production secret guidance.
- **`chirp check` mirrors `app.check()`.** CLI output, warnings-as-errors, and
  coverage must match contract behavior.
- **`chirp freeze` is user-facing.** Static output, live blocks, relative URLs,
  and search metadata need docs/tests with behavior changes.
- **Generated tests use repo conventions.** Async tests need the configured
  pytest style and optional deps.
- **No fabricated flags.** Every documented flag must trace to parser code.
- **Scaffold deps stay current.** Generated `pyproject.toml` must match public
  package names/extras.

## Contract Checklist

When this domain changes, check:

- `src/chirp/cli/__init__.py`, `_new.py`, `_run.py`, `_check.py`, `_routes.py`,
  `_resolve.py`, `_freeze.py`, `_makemigrations.py`, `_security_check.py`.
- `src/chirp/cli/templates/` — generated app code, tests, pyproject, AGENTS
  guidance, security defaults.
- `src/chirp/freeze.py` when freeze behavior changes.
- README quick start, CLI docs/site pages, examples, scaffolds, changelog.
- `tests/cli/`, `tests/test_cli.py`, `tests/test_cli_new.py`,
  `tests/test_cli_resolve.py`, `tests/test_cli_check.py`,
  `tests/test_freeze_*.py`.
- `scripts/check_changelog_fragments.py` and towncrier config for release CLI
  workflows.

## Advocate

- **Scaffold runtime tests.** Generated projects should boot, pass core checks,
  and prove auth/security defaults.
- **Flag/docs parity tests.** CLI docs should not mention flags parser code
  does not accept.
- **Freeze diagnostics.** Bad links, missing live blocks, and search metadata
  drift should produce actionable output.
- **Example alignment.** Examples and scaffolds should demonstrate the same safe
  patterns.

## Do Not

- Add CLI flags that bypass `AppConfig` or `app.check()` semantics.
- Let scaffolds lag security, dependency, or return-type changes.
- Document commands before parser support exists.
- Hand-edit generated output without updating templates.

## Own

**Code:** `src/chirp/cli/`, `src/chirp/freeze.py`, scaffold templates.
**Tests:** CLI, scaffold, freeze, security-check, changelog-fragment tests.
**Docs:** README CLI tables, CLI/site docs, scaffold docs, release guidance.
**Agent artifacts:** scaffolded `AGENTS.md` guidance.
**CODEOWNERS:** manual-confirmation-needed; no CODEOWNERS file exists.
