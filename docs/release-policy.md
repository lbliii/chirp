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

## Furatena Compatibility Canary

Published releases also run an advisory downstream canary against private repository
`lbliii/furatena` at revision `da584bf9fe19ec1376fdc0b23c7fb1b657b026b8`. The release workflow
installs Furatena from its committed `uv.lock`, force-installs the built Chirp wheel without
dependency resolution, verifies Chirp imports from that environment, and runs an 11-test slice
covering navigation, search, narrow htmx/OOB responses, SSE, static assets and mounts, static
export, and structured checks.

The canary runs alongside PyPI publication and is deliberately non-blocking. Its result is release
evidence: a failure must be triaged and recorded, but it does not stop the already-published release.
The workflow summary separates the likely ownership boundary:

- Checkout, missing secret, or revision mismatch: Chirp release-harness owner.
- Locked dependency installation: Furatena owner, with the pinned lockfile as evidence.
- Wheel installation or provenance assertion: Chirp packaging owner.
- Compatibility-test failure: Chirp and Furatena owners compare the pinned suite with the last
  released Chirp wheel before assigning the regression.

`FURATENA_CANARY_TOKEN` must be a fine-grained token with read-only Contents access to the private
Furatena repository. Rotate it under the normal repository-secret policy. Review the pin and test
slice before every Chirp minor release, whenever Furatena changes its lockfile or framework-facing
test surface, and at least quarterly. Pin updates should be isolated, explain the compatibility
delta, and pass once with the current released wheel before becoming release evidence.
