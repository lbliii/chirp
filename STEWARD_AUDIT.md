# Steward Audit

This file records the Phase 4 self-audit for the steward network bootstrap.
The audit used parallel grouped steward agents covering all scoped stewards.
One grouped agent returned no machine-verified P0/P1/P2 findings before
interruption; the other groups returned the findings below.

## Synthesis

- Accepted and applied: checklist coverage gaps in pages, cache, realtime,
  docs tooling, i18n, extension adapters, CLI resolver coverage, testing helper
  filename, OOB contract matrix coverage, and contract/safety evidence wording.
- Accepted and applied: overclaimed steward invariants for safe URL
  normalization, Redis missing-extra guidance, tool event failure/status data,
  validation result deep immutability, return-type frozen status, changelog
  fragment checker breadth, and plan completed-folder status.
- Accepted and applied with collateral: AI/Markdown optional-extra drift in
  example/site install commands and stale `makemigrations <app>` site command.
- Deferred: no source behavior changes for Redis import guards, safe URL
  normalization, tool failure events, or validation deep immutability. The
  steward files now mark these accurately as gaps or narrower current behavior.
- Convergence: the Markdown/AI optional-extra finding was treated as P0 because
  two stewards independently encode the same install-command invariant.

## Findings

Steward: Filesystem Pages And Shell
Area: Contract Checklist coverage
Severity: P2
Invariant: Pages steward owns sections, layout chains, and route debug
behavior.
Evidence: `src/chirp/pages/renderer.py`, `src/chirp/pages/sections.py`, and
`src/chirp/pages/debug.py` existed but were absent from
`src/chirp/pages/AGENTS.md`.
User Impact: Reviewers could miss layout-chain rendering, section context, or
route-debug regressions.
Required Fix: Add those files to the pages checklist.
Required Proof: `rg -n "renderer.py|sections.py|debug.py"
src/chirp/pages/AGENTS.md`.
Collateral: no collateral: steward checklist only.
Confidence: High
Verification Status: machine-verified

Steward: Cache
Area: Contract Checklist coverage
Severity: P2
Invariant: Cache key generation belongs in the cache checklist.
Evidence: `src/chirp/cache/key.py` existed but was absent from
`src/chirp/cache/AGENTS.md`.
User Impact: Cache-variant changes could skip the key module.
Required Fix: Add `key.py` to the checklist.
Required Proof: `rg -n "key.py" src/chirp/cache/AGENTS.md`.
Collateral: no collateral: steward checklist only.
Confidence: High
Verification Status: machine-verified

Steward: Realtime
Area: Contract Checklist coverage
Severity: P2
Invariant: SSE wire formatting and lifecycle source belongs in the realtime
checklist.
Evidence: `src/chirp/realtime/sse.py` existed but was absent from
`src/chirp/realtime/AGENTS.md`.
User Impact: Reviewers could miss heartbeats, disconnect cleanup, fragment
event names, and per-event error behavior.
Required Fix: Add `sse.py` to the checklist.
Required Proof: `rg -n "sse.py" src/chirp/realtime/AGENTS.md`.
Collateral: no collateral: steward checklist only.
Confidence: High
Verification Status: machine-verified

Steward: Security Primitives
Area: Safe URL invariant accuracy
Severity: P1
Invariant: Security-sensitive claims must distinguish current behavior from
desired hardening.
Evidence: `src/chirp/security/urls.py` raw-checks redirects; grep found no
normalization helpers in safe URL source/tests.
User Impact: Reviewers could assume whitespace/encoding normalization exists.
Required Fix: Narrow steward wording to require verification before claiming
normalization.
Required Proof: `rg -n "normalize|strip|urlparse|unquote"
src/chirp/security/urls.py tests/test_safe_url.py`.
Collateral: no collateral: steward wording only.
Confidence: High
Verification Status: machine-verified

Steward: Cache
Area: Optional Redis failure guidance
Severity: P2
Invariant: Missing optional Redis dependencies need actionable guidance.
Evidence: `src/chirp/cache/backends/redis.py` imports `redis.asyncio` directly;
no cache Redis missing-extra test or guarded import was found.
User Impact: Users can receive raw import failures.
Required Fix: Mark this as a current gap in steward guidance.
Required Proof: grep for Redis import guard/tests before claiming implemented
behavior.
Collateral: no collateral: steward wording only.
Confidence: High
Verification Status: machine-verified

Steward: MCP Tools
Area: Tool call event contract
Severity: P1
Invariant: Event guidance must match event fields actually emitted.
Evidence: `ToolCallEvent` carries `tool_name`, `arguments`, `result`,
`timestamp`, and `call_id`; failures return JSON-RPC errors without failed
events.
User Impact: Steward guidance overstated status/error observability.
Required Fix: Narrow wording to success events unless source/tests add failure
events.
Required Proof: inspect `src/chirp/tools/events.py`, `registry.py`, and
`handler.py`.
Collateral: no collateral: steward wording only.
Confidence: High
Verification Status: machine-verified

Steward: Markdown Optional Extra / AI Optional Extra
Area: Optional-extra drift in AI/LLM examples
Severity: P0
Invariant: Examples importing `chirp.markdown` must install the markdown
extra.
Evidence: `examples/chirpui/llm_playground/app.py`,
`examples/chirpui/rag_demo/app.py`, and `site/content/docs/examples/rag-demo.md`
used Markdown while install commands omitted `markdown`.
User Impact: Copy-paste setup could fail for fresh installs.
Required Fix: Add `markdown` to affected install commands.
Required Proof: `rg -n "chirp\\[ai|from chirp\\.markdown|\\| markdown"
examples site/content`.
Collateral: example app comments, example READMEs, site example page.
Confidence: High
Verification Status: machine-verified

Steward: CLI And Scaffolds
Area: CLI docs parity and parser coverage
Severity: P1
Invariant: Documented CLI arguments must trace to parser code.
Evidence: parser requires `makemigrations --db --schema`, while site docs used
`chirp makemigrations <app>`; `_resolve.py` and `tests/test_cli_resolve.py`
were absent from CLI steward checklist.
User Impact: Users could copy a broken command and reviewers could miss resolver
changes.
Required Fix: Correct site docs and checklist.
Required Proof: inspect `src/chirp/cli/__init__.py`,
`site/content/docs/get-started/installation.md`, `_resolve.py`, and resolver
tests.
Collateral: site docs and CLI steward file.
Confidence: High
Verification Status: machine-verified

Steward: Docs Tooling
Area: Docs MCP tool ownership
Severity: P2
Invariant: Docs tooling checklist must cover all docs-plugin behavior.
Evidence: `src/chirp/docs/tools.py` and `tests/docs/test_tools.py` existed but
were absent from `src/chirp/docs/AGENTS.md`.
User Impact: Docs MCP exposure could bypass steward review.
Required Fix: Add source/test files to checklist.
Required Proof: `rg -n "tools.py|test_tools.py" src/chirp/docs/AGENTS.md`.
Collateral: no collateral: steward checklist only.
Confidence: High
Verification Status: machine-verified

Steward: i18n Optional Surface
Area: Formatting helper ownership
Severity: P2
Invariant: i18n checklist should cover all source files and tests in the
surface.
Evidence: `src/chirp/i18n/formatting.py` and formatting tests existed but were
absent from the i18n steward checklist.
User Impact: Formatting behavior could drift without directed review.
Required Fix: Add formatting source/tests to checklist.
Required Proof: `rg -n "formatting.py|test_i18n.py" src/chirp/i18n/AGENTS.md`.
Collateral: no collateral: steward checklist only.
Confidence: High
Verification Status: machine-verified

Steward: Validation
Area: Immutability wording
Severity: P2
Invariant: Immutability claims must distinguish frozen shells from mutable
nested state.
Evidence: `ValidationResult` is frozen/slotted but carries mutable dict
fields.
User Impact: Reviewers could treat validation results as deeply immutable.
Required Fix: Narrow steward wording to frozen/slotted result shells.
Required Proof: inspect `src/chirp/validation/result.py`.
Collateral: no collateral: steward wording only.
Confidence: High
Verification Status: machine-verified

Steward: Protocol And Negotiation
Area: Dispatch-order evidence
Severity: P2
Invariant: Negotiation-order receipts must include actual branches.
Evidence: actual cases include `InlineTemplate` and `LayoutSuspense`, while the
code docstring omits them.
User Impact: Reviewers could miss return branches.
Required Fix: Update steward wording to require checking actual `case`
branches.
Required Proof: `rg -n "case InlineTemplate|case LayoutSuspense"
src/chirp/server/negotiation.py`.
Collateral: no collateral: steward wording only.
Confidence: High
Verification Status: machine-verified

Steward: Rendering
Area: Frozen return-type invariant
Severity: P2
Invariant: Return-type mutability claims must cover the real surface.
Evidence: `MutationResult`/`FormAction` are slotted but not frozen.
User Impact: Reviewers could assume frozen behavior that source does not
provide.
Required Fix: Narrow steward wording and call out slotted-but-not-frozen return
types.
Required Proof: inspect `src/chirp/templating/returns.py`.
Collateral: no collateral: steward wording only.
Confidence: High
Verification Status: machine-verified

Steward: Contract Checks
Area: Rule orchestration receipt
Severity: P2
Invariant: Rule-family evidence must cite actual imports/invocations.
Evidence: safety checks are imported/invoked later than the top import block;
cache-related contract coverage is primarily vary/cache tests, not a dedicated
cache rule import.
User Impact: Reviewers could overread the top import receipt.
Required Fix: Split steward wording and checklist coverage.
Required Proof: grep checker for rule imports, `rules_safety`, cache, and
vary.
Collateral: no collateral: steward wording only.
Confidence: High
Verification Status: machine-verified

Steward: Contract Tests
Area: OOB matrix coverage
Severity: P2
Invariant: High-risk contract regression modules should be named directly.
Evidence: `tests/contracts/test_register_oob_region_matrix.py` was absent from
contract-test and templating checklists.
User Impact: OOB registry changes could miss matrix coverage.
Required Fix: Add matrix test to checklists.
Required Proof: `rg -n "test_register_oob_region_matrix"
tests/contracts/AGENTS.md src/chirp/templating/AGENTS.md`.
Collateral: no collateral: steward checklist only.
Confidence: High
Verification Status: machine-verified

Steward: Changelog Fragments
Area: Changelog fragment validation
Severity: P2
Invariant: Validation claims must match actual checker behavior.
Evidence: the script only rejects leading Markdown list dashes; filename
convention is documented/configured separately.
User Impact: Maintainers could assume broader validation than exists.
Required Fix: Narrow steward wording.
Required Proof: inspect `.pre-commit-config.yaml`,
`scripts/check_changelog_fragments.py`,
and `changelog.d/README.md`.
Collateral: no collateral: steward wording only.
Confidence: High
Verification Status: machine-verified

Steward: Planning And Roadmap
Area: Plan status hygiene
Severity: P2
Invariant: Completed planning artifacts should not contradict status guidance.
Evidence: files under `plan/completed/` still preserve `Status: Draft`
headers.
User Impact: Agents could misread completed-folder artifacts as current drafts
or shipped proof without context.
Required Fix: Narrow steward wording to require explicit status signal and
roadmap/context when preserved headers disagree with folder location.
Required Proof: `rg -n "^\\*\\*Status\\*\\*: Draft" plan/completed`.
Collateral: no collateral: steward wording only.
Confidence: High
Verification Status: machine-verified

## Incomplete Audit

The Public Surface/App/HTTP/Routing grouped audit agent returned:

> No machine-verified P0/P1/P2 findings were completed before the interruption.

Verification Status: machine-verified for the agent result; no actionable
findings were accepted from that group.
