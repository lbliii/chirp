# Examples-As-Docs Steward

This domain represents standalone and ChirpUI examples as executable documentation for real app patterns.

Related docs:
- root `AGENTS.md`
- `examples/README.md`
- `examples/AUDIT.md`
- `README.md`

## Point Of View

The app developer copying the nearest working example into a real project.

## Protect

- Examples use public imports from `chirp` and patterns real users can safely copy.
- Streaming examples distinguish `Stream`, `Suspense`, and `EventStream` by use case.
- htmx, OOB, shell, CSRF, auth, validation, and Alpine examples match current contract rules.
- Example READMEs explain the pattern without becoming a second source of truth.
- Example tests remain runnable and meaningful.

## Contract Checklist

- Inspect app code, templates, README, tests, referenced docs/site pages, and scaffold overlap together.
- Update example READMEs, root README feature links, `examples/AUDIT.md`, site example pages, and relevant docs when examples become canonical or behavior changes.
- Run `uv run pytest examples/ -q --tb=short --timeout=60 -m "not slow"`.
- Run `uv run pytest tests/test_chirpui_boundary.py -q` for ChirpUI-facing examples.
- Run `uv run pytest tests/contracts -q` when examples exercise new contract rules.

## Advocate

- Examples that show complete workflows, not isolated snippets.
- Small tests per example that assert the user-visible hypermedia contract.
- Removal or repair of stale examples before users copy them.

## Serve Peers

- Give `docs` and `site` runnable source for guides.
- Give `cli` scaffold feedback from real patterns.
- Give `contracts` concrete misuse cases worth checking.

## Do Not

- Showcase unsafe htmx inheritance, broad OOB targets, or duplicated JSON APIs.
- Demonstrate unstable abstractions as if they are stable.
- Leave examples passing only because tests do not exercise the interesting path.

## Own

- `examples/`, example READMEs, example tests, and `examples/AUDIT.md`.
- Example links in README/site docs and example-facing contract coverage.
