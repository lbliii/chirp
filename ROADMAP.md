# Chirp Release Roadmap

Status: release-gate reference and backlog index — not an active task list.

**Authoritative backlog:** <https://github.com/lbliii/chirp/issues>  
**Active maintainer batch:** `.context/todos.md` (links only)  
**Historical synthesis:** `plan/roadmap.md`

Read GitHub issues for what to build next, scope, and acceptance. Package
version: `pyproject.toml` and `CHANGELOG.md`.

## Backlog

- Open issues: <https://github.com/lbliii/chirp/issues>
- Open PRs: <https://github.com/lbliii/chirp/pulls>

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
