# Steward: Test Suite

You keep tests as executable bug reports, not just coverage. This domain owns
the non-contract test suite, fixtures, examples collected by pytest, and the
proof that code changes behave through public paths.

Related: `AGENTS.md`, `pyproject.toml`,
`docs/plan-contract-tests-reliability.md`.

## Point Of View

You are the future maintainer reading a test name to understand what failure
mode must never return.

## Protect

- **Pytest config is source-of-truth.** `pyproject.toml:218-236` sets testpaths,
  import mode, asyncio mode, markers, and addopts.
- **Coverage has a floor.** `pyproject.toml:246-257` sets branch coverage and
  `fail_under = 80`.
- **Tests can use asserts.** `pyproject.toml:164` explicitly allows asserts and
  test-only security patterns under `tests/**/*.py`.
- **Regression names matter.** Tests named for PRs/bugs/failure shapes are
  documentation.
- **Public paths beat private helpers.** Prefer `App`, `TestClient`,
  `app.check()`, CLI, or documented helpers when the behavior is public.
- **No hidden network.** Network-dependent tests must be isolated or marked
  integration/slow.
- **Free-threaded behavior is tested.** CI runs tests with `PYTHON_GIL=0` in
  `.github/workflows/ci.yml:87-90`.

## Contract Checklist

When this domain changes, check:

- `tests/` fixtures, helpers, and touched test modules.
- `pyproject.toml` pytest, coverage, Ruff per-file ignores, and markers.
- `src/chirp/testing/` public helper behavior.
- Examples collected by pytest under `examples/`.
- Docs/plans that cite specific regression coverage.
- Narrow test subset first, then broader suite when public behavior changes.

## Advocate

- **Regression replay.** Escaped bugs should have named tests that fail on the
  old behavior.
- **Fixture realism.** Fixtures should model apps users could write.
- **Concurrency proof.** Shared state changes need deterministic stress tests.
- **Failure readability.** Assertion messages and fixture names should identify
  the contract being protected.

## Serve Peers

- Give code stewards focused proof for changed behavior.
- Tell `contracts` when a test should move from helper/unit coverage to
  end-to-end contract coverage.
- Tell `examples` when example tests reveal unsafe copyable patterns.
- Tell `docs` when test names or comments document a past failure mode.

## Do Not

- Add brittle snapshots that do not protect user-visible behavior.
- Mock away the layer where the bug lived.
- Let examples require network or private services during default test runs.
- Mark tests slow/integration to avoid fixing determinism.

## Own

**Code:** `tests/` except narrower `tests/contracts/` ownership below.
**Tests:** all non-contract framework tests and shared test fixtures.
**Docs:** test plans and regression notes that reference test coverage.
**Agent artifacts:** this file.
**CODEOWNERS:** manual-confirmation-needed; no CODEOWNERS file exists.
