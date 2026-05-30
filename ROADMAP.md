# Chirp Release Roadmap

Status: active next-release roadmap for the 0.7.x line.

Authoritative planning lives in `plan/roadmap.md`. This root file is the
release-manager view: what should land next, what proof closes the release, and
what stays out of scope.

## Current Ground Truth

- Latest released version: `0.7.0` (`CHANGELOG.md`, tag `v0.7.0`).
- Current package version: `0.7.0` in `pyproject.toml`.
- Open GitHub issues checked on 2026-05-30: none.
- Open GitHub PRs checked on 2026-05-30: PR #131, request-aware filesystem
  page actions.
- Current release-prep branch: `codex/next-release-roadmap`, with native
  DevTools debug runtime and request-aware `_actions.py` dispatch prepared for
  `0.7.1`.

## 0.7.1 Candidate Scope

The next release should stay patch-sized unless additional user-visible API
work is accepted. The current candidate is:

1. Ship native DevTools debug runtime follow-through already on `main`.
2. Ship request-aware filesystem `_actions.py` dispatch so action handlers and
   request-aware `app.provide()` factories preserve per-request service scope.
3. Keep planning collateral honest for the post-0.7 roadmap.
4. Verify release gates, compile the changelog, and prepare the site release
   page before tagging.

If tenant/base-path URL helpers, new contract categories, or optional-extension
APIs are added, promote the work to a minor release plan before implementation.

## Next Priorities After 0.7.1

1. Fragment/SSE example audit and browser smoke.
2. Contract and reactive docs parity.
3. Mounted page contract confidence for downstream product-shaped apps.
4. Request URL scope RFC decision before code.
5. Production form and CSRF proof.
6. App-shell, OOB, and SSE reconnect proof.
7. Diagnostics and compact product-shaped fixtures.
8. Extension contract maturity without making optional packages core.

## Release Gates

Before cutting a 0.7.x release:

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

Compile `CHANGELOG.md` only at release time.

## Not Now

- New return types.
- JSON/API side channels for product data.
- Core dependency on `chirp-ui`.
- Product schemas, workflows, moderation, or forum implementation in Chirp.
- Contract severity promotions without maintainer review.
