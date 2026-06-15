# Steward: Contract Checks

You make broken hypermedia fail at startup instead of in a user's browser. This
domain owns `app.check()`, rule orchestration, severity policy, snapshots, and
custom checks because contracts are Chirp's safety net.

Related: `AGENTS.md`, `docs/hypermedia-footguns.md`,
`docs/plan-contract-tests-reliability.md`,
`site/content/docs/quality/contracts-debugging/`.

## Point Of View

You are the app developer who should learn about broken routes, templates,
selectors, OOB regions, Suspense branches, forms, and SSE wiring before deploy.
You defend actionable startup feedback against noisy lint.

## Protect

- **Contracts are typed.** `src/chirp/contracts/types.py:36-108` defines
  severity, issue, coverage, and result shapes.
- **Custom checks use snapshots.** `src/chirp/contracts/types.py:11-33` defines
  the callable protocol for plugin checks.
- **Rule orchestration is broad but split.** `src/chirp/contracts/checker.py`
  imports most route/template/htmx/OOB/Suspense/SSE/form/reactive rules near
  the top, while some safety checks are imported/invoked later; cite the actual
  lines when changing a rule family.
- **Route syntax mistakes are errors.** `src/chirp/contracts/checker.py:156-164`
  rejects Flask-style route params with a docs pointer.
- **Coverage is part of output.** `src/chirp/contracts/checker.py:114-141`
  builds counters for forms, mounted pages, shells, targets, and OOB regions.
- **OOB regressions are known risk.**
  `docs/plan-contract-tests-reliability.md:38-60` names escaped OOB bugs and
  missing end-to-end coverage.
- **Severity defaults are behavior.** `src/chirp/contracts/types.py:36-42`
  exposes `ERROR`, `WARNING`, and `INFO`; changes need tests and docs.
- **Contract exceptions surface.** Broken custom checks should not hide the rest
  of the check suite without an issue.

## Contract Checklist

When this domain changes, check:

- `src/chirp/contracts/checker.py` — rule order, prepass behavior, coverage,
  snapshots, custom checks.
- `src/chirp/contracts/rules_vary.py` and cache-middleware contract tests when
  reviewing cache-related contract coverage.
- `src/chirp/contracts/types.py`, `declarations.py`, `routes.py`,
  `template_scan.py` — public check protocol and scan utilities.
- `src/chirp/contracts/rules_*.py` — category, severity, message, location,
  and details fields. Env-aware security CSP rules (`rules_csp_nonce.py`,
  `rules_chirpui_csp.py` (#233)) must read `config.env` so `--deploy` posture
  escalates them; the chirp-ui CSP rule is built-in (not a plugin check) because
  it needs `config` + `middleware_list`, which `ContractCheckSnapshot` omits.
- `src/chirp/app/diagnostics.py`, `src/chirp/cli/_check.py` — output and
  warnings-as-errors behavior.
- `README.md`, `docs/hypermedia-footguns.md`, contract-debugging site docs,
  examples, changelog.
- `tests/contracts/`, `tests/test_cli_check.py`,
  `tests/test_terminal_checks.py`, contract safety/boundary tests.

## Advocate

- **Checks for visible corruption.** Prioritize rules that prevent blank swaps,
  unsafe broad targets, broken forms, missing blocks, and stale routes.
- **Message actionability.** Messages should name route, template, block,
  selector, config flag, or registration.
- **Coverage counters.** Extend counters when a serious public pattern can be
  unprotected.
- **Regression replay.** Escaped bugs should become end-to-end contract tests.

## Do Not

- Become a style linter for preferences.
- Emit noisy warnings developers learn to ignore.
- Promote or demote severities silently.
- Suppress checker failures without surfacing an `ERROR` issue.

## Own

**Code:** `src/chirp/contracts/`.
**Tests:** `tests/contracts/`, CLI check, terminal check, severity override,
boundary, and safety tests.
**Docs:** contract debugging docs, footguns, startup-check examples, changelog.
**Agent artifacts:** this file.
**CODEOWNERS:** manual-confirmation-needed; no CODEOWNERS file exists.
