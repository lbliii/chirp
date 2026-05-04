# Changelog Steward

This domain represents towncrier fragments under `changelog.d/`: the release-note inputs that turn public behavior changes, fixes, deprecations, removals, and security updates into `CHANGELOG.md`.

Related docs:
- root `AGENTS.md`
- `changelog.d/README.md`
- `docs/release-policy.md`
- `docs/public-api.md`
- `pyproject.toml`

## Point Of View

The release operator and app author reading upgrade notes to understand what changed, whether migration is required, and why a public contract moved.

## Protect

- Fragment filenames follow `<+slug>.<type>.md` using the towncrier types configured in `pyproject.toml`.
- Fragment bodies are plain text without a leading `-`; towncrier owns the bullet.
- Public API, behavior, security, dependency, and migration-impact changes get fragments in the same PR.
- Breaking or compatibility-sensitive entries include migration notes or explicitly say why none are needed.
- Release notes do not overclaim performance, stability, or production readiness without evidence.

## Contract Checklist

- Inspect changed public/API/CLI/protocol/docs/examples/scaffold behavior and decide whether a fragment is required.
- Update `docs/release-policy.md`, `docs/public-api.md`, README, or site release guidance when changelog policy changes.
- Run `uv run python scripts/check_changelog_fragments.py` when editing fragment format or existing fragments.
- Run `make changelog-draft` or `uv run towncrier build --draft` when previewing release-note output.
- Run `make changelog-check` or `uv run towncrier check --compare-with origin/main` when validating branch fragment presence.

## Advocate

- Changelog entries that name the user-visible contract, not just internal file changes.
- Migration notes for stable API changes and compatibility-sensitive provisional changes.
- Release-note previews before release branches compile fragments.

## Serve Peers

- Tell `public surface`, `cli`, `contracts`, `templating`, `data`, `security`, and `docs` when their user-facing changes need release notes.
- Give `docs` and `site` accurate release context.
- Give `benchmarks` a place to cite performance evidence without turning claims into marketing.

## Do Not

- Add fragments for purely internal refactors with no user-visible impact.
- Start fragment bodies with `- `.
- Compile/delete fragments outside the release workflow.
- Hide breaking changes in generic "updates" wording.

## Own

- `changelog.d/`, `changelog.d/README.md`, and fragment format policy.
- `scripts/check_changelog_fragments.py` as the fragment-format maintenance check.
- Towncrier fragment type coordination in `pyproject.toml`.
