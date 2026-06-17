# Contributing to Chirp

Thanks for contributing! Chirp targets **Python 3.14+** (free-threading, modern
syntax). The development guide in [`CLAUDE.md`](CLAUDE.md) is the canonical
source for architecture, conventions, and the full build/test workflow.

## Quick start

```bash
uv sync --group dev          # Install dev dependencies
uv run poe hooks-install     # Install git hooks (commit-time + pre-push preflight)
```

## Before you push: run the preflight

Run the fast pre-push invariant check before pushing or opening a PR:

```bash
uv run poe preflight   # or: make preflight
```

`preflight` runs only the cheap whole-repo invariants and exits non-zero on the
first failure:

- `ruff check .` — lint
- `ruff format . --check` — formatting
- `ty check src/chirp/` — type check
- `pytest tests/test_lazy_imports.py tests/test_public_api_docs.py` — public-API
  snapshot + docs-coverage invariants

It **does not** run the full test suite, so it finishes in seconds. It catches
the public-API-snapshot / docs-coverage / format / ty failure class locally
instead of via the full ~8-minute CI test round-trip. It is also wired as a `pre-push`
hook in `.pre-commit-config.yaml`.

For the full test suite, type checking details, changelog fragments, and
release gates, see [`CLAUDE.md`](CLAUDE.md) ("Build & Test") and `ROADMAP.md`.

## Linking a PR to an issue (the closure-acceptance gate)

If your PR closes an issue, say so in the description with a GitHub
[closing keyword](https://docs.github.com/en/issues/tracking-your-work-with-issues/linking-a-pull-request-to-an-issue):
`Closes #123`, `Fixes #123`, or `Resolves #123`.

Chirp gates this. A PR that *closes* an issue must ship proof the issue is
actually done, so "done" is a fact the suite proves rather than a claim
reconciled weeks later. CI runs a **`closure-acceptance`** check that requires
**one** of:

- **An acceptance test (preferred).** At least one test decorated with
  `@pytest.mark.issue(123)` that exercises the issue's acceptance criteria.
- **An explicit exemption.** For issues with no testable runtime behavior
  (docs, positioning, tooling), add a line to the PR **description**:

  ```
  Acceptance: n/a (docs-only)
  ```

  The `(reason)` is required and is audited — a deliberate, visible
  declaration, not a way to skip a test that should exist.

If your PR does **not** close an issue, the gate does not apply — you can still
reference an issue with `Refs #123` and let a maintainer close it. See
[`docs/backlog-automation.md`](docs/backlog-automation.md) for the rationale.

> New contributor? You don't have to memorize this — the pull-request template
> walks you through it when you open a PR.

## Backlog and roadmap

The **live GitHub backlog is authoritative** for open work:

- Issues: <https://github.com/lbliii/chirp/issues>
- Pull requests: <https://github.com/lbliii/chirp/pulls>

Planning detail and ranking live in `plan/roadmap.md`. Do not rely on any
static "no open issues" count baked into a Markdown file — those go stale
silently (a `roadmap-staleness` pre-commit hook guards against re-introducing
one).
