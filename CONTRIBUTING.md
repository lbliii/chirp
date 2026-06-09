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
instead of via a ~20-minute CI round-trip. It is also wired as a `pre-push`
hook in `.pre-commit-config.yaml`.

For the full test suite, type checking details, changelog fragments, and
release gates, see [`CLAUDE.md`](CLAUDE.md) ("Build & Test") and `ROADMAP.md`.

## Backlog and roadmap

The **live GitHub backlog is authoritative** for open work:

- Issues: <https://github.com/lbliii/chirp/issues>
- Pull requests: <https://github.com/lbliii/chirp/pulls>

Planning detail and ranking live in `plan/roadmap.md`. Do not rely on any
static "no open issues" count baked into a Markdown file — those go stale
silently (a `roadmap-staleness` pre-commit hook guards against re-introducing
one).
