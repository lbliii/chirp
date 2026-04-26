# Release Policy

Chirp is pre-1.0, but application authors should still be able to trust minor releases. The rules
below make release changes explicit without pretending the public surface is frozen forever.

## Versioning

- Patch releases fix bugs, docs, examples, and dependency floors without changing intended public
  behavior.
- Minor releases may add stable or provisional API and may adjust provisional shapes when the
  contract improves.
- Breaking changes to stable API require a changelog entry and a migration note.

## API Tiers

The blessed import path is `from chirp import ...`. Top-level exports are classified in
`docs/public-api.md` and tested against `chirp.__all__`.

| Tier | Promise |
|------|---------|
| Stable | Intended for application code. Breaking changes need deprecation first unless there is a security or data-loss class bug. |
| Provisional | Supported, documented when useful, but still settling before 1.0. Changes still need changelog coverage. |
| Debug / advanced | Available for diagnostics and framework tooling. Prefer stable return types and app methods for normal apps. |
| Internal | Anything not exported from `chirp.__all__`. No compatibility promise. |

## Deprecations

Stable API deprecations use `DeprecationWarning` and should stay in place for at least one minor
release before removal. The warning message should name the replacement and, when useful, the
guide or changelog entry that explains the migration.

Provisional API may move faster, but removals still need a changelog entry. If a provisional
change can corrupt rendered UI or hide a contract failure, prefer a compatibility shim for one
minor release.

## Release Gates

Before cutting a release:

```bash
uv run ruff check .
uv run ruff format . --check
uv run ty check src/chirp/
uv run pytest tests/ -q --tb=short --timeout=60 -m "not slow"
uv run pytest examples/ -q --tb=short --timeout=60 -m "not slow"
uv run python -m benchmarks.core --iterations 250 --route-count 100 \
  --output .benchmarks/core-latest.json
uv run towncrier build --version <version> --draft
uv build
```

Compile the changelog only at release time:

```bash
uv run towncrier build --version <version> --yes
```

The benchmark artifact is release evidence, not a marketing claim. Public release notes should
say "synthetic benchmarks" or "internal regression workloads" unless they are backed by a
separate production-like benchmark plan.
