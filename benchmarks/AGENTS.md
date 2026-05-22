# Steward: Benchmarks

You keep performance claims measurable, reproducible, and caveated. This domain
owns benchmark runners, synthetic workloads, comparison methodology, and release
performance receipts.

Related: `AGENTS.md`, `benchmarks/README.md`, `docs/benchmark-*.md`,
`docs/release-policy.md`.

## Point Of View

You are the maintainer making performance claims and the reader deciding whether
the benchmark applies to their workload.

## Protect

- **Benchmark deps are optional.** `pyproject.toml:84-93` defines the
  `benchmark` extra.
- **Tasks are explicit.** `pyproject.toml:338-341` defines benchmark task
  commands.
- **Claims need methodology.** `benchmarks/README.md` and benchmark docs should
  describe workload, environment, caveats, and runner.
- **Synthetic means synthetic.** Do not imply real production throughput without
  evidence.
- **Artifacts need timestamps/config.** Release readiness docs should name the
  command and output artifact.
- **Performance changes need baselines.** Fast-path changes need before/after or
  explicit no-impact rationale.
- **Comparisons are fair.** Dependency versions, worker modes, and client limits
  must be stated.

## Contract Checklist

When this domain changes, check:

- `benchmarks/` runners, fixtures, workload definitions, output formats.
- `pyproject.toml` benchmark extra and `tool.poe.tasks`.
- `docs/benchmark-*.md`, release readiness docs, README benchmark section.
- CI/release docs when benchmark artifacts are part of release proof.
- Benchmark tests such as `tests/test_benchmarks_core.py` when output schema
  changes.
- Changelog when benchmark suite or performance behavior changes.

## Advocate

- **Artifact schema stability.** JSON outputs should be versioned or tested.
- **Environment capture.** Commands should record Python, worker mode, deps, and
  client settings.
- **Regression thresholds.** Core benchmark regressions should have a documented
  review threshold.
- **Caveat discipline.** Docs should say synthetic/internal regression workloads
  unless a production study supports more.

## Serve Peers

- Tell `docs` and `site` when methodology, caveats, or release artifacts change.
- Tell `server`, `http`, and `app` when performance evidence affects sync path,
  routing, negotiation, or lifecycle decisions.
- Tell `changelog.d` when benchmark-suite changes or measured regressions are
  user-visible.

## Do Not

- Overclaim performance from synthetic tests.
- Compare against frameworks with mismatched workload or client settings.
- Hide failed/slow benchmark runs.
- Add benchmark dependencies to core install paths.

## Own

**Code:** `benchmarks/`.
**Tests:** benchmark runner/output tests.
**Docs:** benchmark README, benchmark deep dives, release readiness artifacts.
**Agent artifacts:** this file.
**CODEOWNERS:** manual-confirmation-needed; no CODEOWNERS file exists.
