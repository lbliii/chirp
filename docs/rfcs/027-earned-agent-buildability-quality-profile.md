# RFC 027: Earned Agent-Buildability Quality Profile

**Status:** Proposed decision collateral; blocked on evidence and steward sign-off

**Issue:** [#887](https://github.com/lbliii/chirp/issues/887)

**Parent epic:** [#886](https://github.com/lbliii/chirp/issues/886)

**Parent saga:** [#876](https://github.com/lbliii/chirp/issues/876)

**Proposed profile:** `agent-buildability-quality-v1` (repository-internal)

**Created:** 2026-08-03

## Summary

An application earns Chirp's agent-buildability quality receipt only when
independent evidence proves every required dimension. The report preserves
`pass`, `fail`, `unobserved`, `suppressed`, `human_review`, and
`not_applicable` as separate states. It has no numeric score. Static inspection
cannot stand in for an executed route or browser, TestClient evidence cannot
stand in for DOM behavior, and a suppression or unknown can never render as
clean.

This RFC freezes a proposed claim matrix and report shape for issue #888. It
does not implement the gate or approve a public command, API, AppConfig field,
severity/default change, deploy policy, or product claim. Acceptance remains
blocked because the dynamic accessibility edges in #687, enhancement-tier
diagnostics in #724, JavaScript-disabled browser proof in #725, a clean
maintained canary, and affected steward sign-offs are not available.

## 1. Decision boundary

The quality profile is a read-only composition of evidence owned elsewhere.
It never rescans templates, reimplements a security rule, infers browser
coverage from static topology, or changes the meaning of an underlying result.

The v1 outcome is categorical:

- `pass`: authoritative evidence executed and proved the dimension's declared
  cases with no unresolved findings;
- `fail`: authoritative evidence found a required behavior or posture broken;
- `unobserved`: required evidence did not run, does not exist, or cannot prove
  the claim;
- `suppressed`: a finding, assertion, warning policy, path, or required case was
  disabled, ignored, waived, or removed;
- `human_review`: the profile deliberately delegates the decision to a named
  human review and no completed receipt is attached; and
- `not_applicable`: source-backed discovery proves the application has no such
  surface and the claim does not require one.

`unknown` is serialized as `unobserved`; there is no clean-looking unknown
state. A dimension cannot become `pass` merely because its evidence source
emitted no record: absence must itself be an authoritative, executed result.

### 1.1 Overall result

The overall report is:

- `fail` when any required dimension is `fail` or `suppressed`;
- `incomplete` when no required dimension failed but any required dimension is
  `unobserved` or `human_review`; and
- `pass` only when every required dimension is `pass` or a valid
  `not_applicable`, all required human reviews are complete, all evidence
  artifacts pass integrity/redaction checks, and all steward sign-offs for the
  profile version are approved.

No score, average, percentage, or “mostly clean” label can override these
boundaries. Measurements such as duration or transition counts are descriptive
only.

### 1.2 Findings, warnings, and suppressions

For an earned receipt, an unresolved `ERROR` or `WARNING` from the configured
or deploy-posture inspection makes its owning dimension `fail`. This is a
quality-profile policy, not a promotion or change to `app.check()` severity.
The application can fix the finding or improve the owning rule through its
normal evidence and compatibility process; it cannot silently waive it.

`INFO` findings are retained. They do not block by default, but they do block a
specific declared claim when their content is authoritative for that claim.
For example, a shipped `nojs_floor` informational finding contradicts an
application's claim that every mutation has a plain-browser success path.

Any severity override, ignored finding, expected failure, coverage exclusion,
deleted required assertion, skipped required scenario, or approved waiver is a
suppression. Suppression is transparent but never clean in v1. A false positive
must be repaired in the evidence owner or the app before launch proof; a human
waiver cannot turn it into `pass`.

## 2. Claim and evidence matrix

Every dimension records its exact claim, authoritative evidence, required
cases, failure meaning, unobserved meaning, and repair surface. Artifact IDs in
the report point to the raw machine or reviewer receipt.

| Dimension | Claim earned by `pass` | Authoritative evidence | Required cases / threshold | Failure meaning | `unobserved` meaning | Repair owner |
| --- | --- | --- | --- | --- | --- | --- |
| `structural_contracts` | Declared routes, templates, blocks, targets, forms, OOB/SSE edges, and extension wiring have no known contract finding. | One structured `app.check()`/inspection result in configured posture, including findings and coverage. | Zero unresolved `ERROR` or `WARNING`; all profile-required coverage facts present; `INFO` retained. | Chirp found broken or risky declared structure, or required coverage is incomplete. | Inspection did not run or the versioned profile cannot represent a required fact. | Owning contract category; never a quality-layer scanner. |
| `production_posture` | The app's declared deploy configuration has no known production-safety finding. | The same app inspected with existing production-posture behavior (`chirp check --deploy` or equivalent accepted inspection result). | Zero unresolved deploy `ERROR` or `WARNING`; exact app/config revision matches the receipt. | A production misconfiguration or unresolved production caution remains. | Deploy posture did not run or used a different revision/config. | Owning deploy/security contract and application config. |
| `security_journeys` | Declared authentication, authorization, session, CSRF, redirect, and audit boundaries behave as required. | Focused tests through public HTTP/TestClient/browser paths plus security contract results; security steward selects applicable cases. | Every declared threat-boundary case passes, including negative/denial paths; no excluded required case. | A protected action succeeds incorrectly, denial/audit behavior is wrong, or a required boundary lacks a test. | Static config passed but runtime security behavior was not exercised. | Application security tests or owning Chirp security surface. |
| `full_page_behavior` | Required journeys work as ordinary HTTP/full-page interactions. | Explicit TestClient/route-smoke cases and browser receipts where browser semantics matter. | All task-packet full-page, success, error, redirect, and malformed-input cases pass. | A required user journey fails or returns the wrong render/status/redirect behavior. | No explicit case exists or only source/static inspection ran. | App behavior/tests; Chirp only for framework-owned failures. |
| `htmx_behavior` | Required enhanced journeys render and swap the intended named surfaces. | TestClient evidence for response intent plus Playwright/DevTools evidence for DOM target, OOB, focus, history, or transport behavior. | Every declared htmx/OOB/SSE path has response and browser observations; no full document enters a fragment target. | Response intent or actual DOM behavior is wrong. | Static target resolution or TestClient response exists without required browser observation. | App/browser test or owning hypermedia behavior. |
| `invalid_form_behavior` | Malformed and invalid inputs preserve values, errors, status, and intended focus/announcement behavior. | TestClient for status/rendered HTML plus browser evidence for focus and dynamic announcements. | Every declared form has malformed, domain-invalid, auth/CSRF-invalid, full-page, and enhanced cases as applicable. | Invalid input corrupts state, hides feedback, uses the wrong status, or loses required browser behavior. | Only happy paths or only static form contracts ran. | App validation/security/browser proof. |
| `transition_coverage` | Every task-declared important compiled transition and request mode was observed. | `TransitionObservation`/`TransitionCoverage`, route smoke, and correlated browser evidence using stable transition IDs. | Set inclusion: all packet-declared transition IDs and modes observed; no percentage threshold. | A required transition was exercised and failed or evidence disagrees with compiled identity. | A compiled edge exists but was not observed; static reachability is never execution. | App tests/observations or compiler correlation issue. |
| `no_javascript_browser` | The declared progressive-enhancement floor completes in a browser with JavaScript disabled. | Playwright context with JavaScript disabled, plus supporting plain-request TestClient cases and accepted enhancement contracts. | All task-declared native navigation, mutation, validation, and fallback journeys pass in the disabled-JS browser. | A required task depends on JavaScript or the fallback is unusable. | Plain HTTP tests pass but disabled-JS browser did not run, or #725 evidence is unavailable. | Application fallback/browser proof; enhancement owner for framework facts. |
| `static_accessibility` | Chirp's currently supported literal accessibility facts have no known finding. | Existing `a11y_*` inspection categories at their shipped severities and source locations. | Zero unresolved `ERROR` or `WARNING`; the report names the exact categories evaluated. | A supported literal accessibility issue remains. | Static rules did not run or required source/composition was unavailable. | Owning accessibility contract. This is not WCAG conformance. |
| `dynamic_accessibility` | Declared focus, live-region, dialog/popover, and motion-independent interaction cases behave as specified. | Accepted compiled declarations from #687 plus Playwright assertions over active element and accessibility-facing DOM; optional axe results are supporting only. | Every applicable dynamic case has both graph/contract and browser evidence; human exploratory accessibility review attached separately. | A declared interaction is broken in the browser or its contract edge is invalid. | Static a11y is clean but dynamic edge/browser evidence is missing. | #687/app browser tests. Never infer from markup alone. |
| `proof_integrity` | Required evidence is complete, unsuppressed, content-addressed, and redacted. | RFC 026 evaluation receipt, artifact-integrity checks, suppression inventory, and redaction report. | Zero missing artifacts, invalid/undeclared interventions, suppressions, bypassed repairs, or unresolved redactions. | The apparent result was weakened, altered, incomplete, or unsafe to publish. | Integrity, suppression, intervention, or redaction validation did not run. | Evaluation harness (#890/#888). |
| `human_review` | A human reviewed only the judgments machines cannot establish and recorded bounded conclusions. | Versioned reviewer checklist with reviewer identity, app revision, sampled journeys, concerns, and disposition. | Product-scope coherence, visible error/copy quality, destructive-action clarity, keyboard/screen-reader exploratory sample, and obvious parallel architecture reviewed; no unresolved launch concern. | Reviewer records an unresolved concern in the bounded checklist. | Required human review has not occurred. | Application/product owner; the gate reports but does not automate taste or truth. |

### 2.1 Valid `not_applicable`

`not_applicable` requires an evidence source that discovered no applicable
surface. It is invalid for the mandatory `structural_contracts`,
`production_posture`, `proof_integrity`, or `human_review` dimensions. It may
apply to a security mechanism, form, htmx, SSE, dialog, or other conditional
case only when the application truly has no such surface and the task packet
does not require it. The reason and evidence artifact are mandatory.

### 2.2 Evidence authority hierarchy

Evidence proves only what its layer observes:

```text
compiled/static inspection -> declared structure and source-backed findings
TestClient/route smoke      -> HTTP, return intent, rendered bytes, state
transition observations    -> executed compiled identities/request modes
Playwright/DevTools         -> actual browser DOM, focus, history, JS/no-JS
human review                -> bounded judgment, not machine correctness
```

A stronger layer does not erase a lower-layer failure, and a lower layer cannot
claim a stronger observation. In particular:

- a resolved fallback edge does not prove a JavaScript-disabled task works;
- a `200` htmx response does not prove the browser swapped the intended node;
- zero static accessibility findings does not prove focus, announcements,
  assistive-technology behavior, or WCAG conformance;
- a passing deploy inspection does not prove authentication or authorization
  journeys; and
- human approval cannot turn missing deterministic evidence into `pass`.

## 3. Proposed report shape

The adjacent
[`027-agent-buildability-quality-v1.schema.json`](027-agent-buildability-quality-v1.schema.json)
defines a strict proposed internal report. Each dimension must carry:

- one stable dimension ID and whether the profile requires it;
- one categorical status;
- the exact bounded claim;
- authoritative evidence-source and artifact references;
- observed and unobserved cases;
- open findings and suppression count;
- failure and unobserved meanings; and
- the owning repair surface.

The report also records profile/app identity, overall result, exclusions,
integrity counts, and contract/security/accessibility sign-offs. The schema can
validate shape and status vocabulary; #888 must validate artifact references,
derive statuses, enforce the overall-state rules, and reject duplicated or
missing dimensions.

### 3.1 Versioning

`agent-buildability-quality-v1` is repository-internal and proposed. A report
pins the profile version, app revision, task packet/receipt when used in an
agent evaluation, evidence-set digest, and the exact required dimension IDs.

Adding optional evidence metadata is compatible within the implementation's
private v1 serializer. Changing a claim, authority, required case, status
meaning, blocking rule, or dimension membership requires a new profile version
and invalidates comparisons with the old profile. Publishing any schema or
command requires separate public-API review.

## 4. Maintained-canary application

The draft matrix was applied to
`examples/standalone/nojs_floor` at the current workspace revision. The
adjacent
[`027-agent-buildability-quality-canary.json`](027-agent-buildability-quality-canary.json)
is deliberately an incomplete/non-product fixture.

Observed evidence:

- nine maintained no-JS TestClient tests pass, including ordinary GET, native
  POST/redirect/GET, `422` validation, and persisted-state assertions;
- configured-posture `chirp check --json --include-info --coverage` returns
  `ok: true` but reports six warnings, including two `a11y_label` findings plus
  `a11y_landmark`, `macro_css`, `security_stack`, and `swap_safety`;
- deploy-posture inspection returns `ok: false`, with `allowed_hosts`,
  `secret_key`, and `security_stack` errors plus warnings;
- the example test suite intentionally sends no `HX-Request` header, so it does
  not prove enhanced behavior;
- the tests model plain-browser HTTP semantics but do not launch a browser with
  JavaScript disabled; and
- no transition-coverage, suppression-inventory, dynamic accessibility, or
  human-review receipt exists for this app.

The correct draft result is `fail`, not clean. That result is useful: the
profile refuses to turn a focused no-JS example into a production, htmx,
accessibility, or agent-buildability claim.

Lucky Cat and Forum Shell were also inspected as existing #346/#347 canaries.
Both configured-posture checks return `ok: true`, but both retain warnings; they
therefore cannot substitute as the required clean maintained app.

## 5. Intentional broken-variant application

Existing evidence was mapped without inventing a new scanner or fixture app:

| Broken variant | Existing authority exercised | Result under draft profile | Limitation / false-result boundary |
| --- | --- | --- | --- |
| Production debug/host/secret/security stack misconfiguration | `tests/contracts/test_deploy_preflight.py`, `test_deploy_nojs_i18n_integration.py`, `test_security_stack_rule.py` | `production_posture: fail`; 45 focused tests passed and prove the owning rules detect accepted cases. | Static posture does not prove auth/authorization journeys. |
| Htmx-only mutation with no plain success path | `tests/contracts/test_nojs_floor.py` and the shipped `nojs_floor` `INFO` finding | `no_javascript_browser: fail` when the app claims the floor; otherwise the finding remains informational. | Handler-source analysis is best effort; disabled-JS browser proof remains #725. |
| Literal missing label/alt/interactive semantics | `tests/contracts/test_accessibility.py` and `test_hypermedia.py` | `static_accessibility: fail` when a finding is present. | Regex/static composition limitations remain; no WCAG or dynamic claim. |
| Focus drop, removed live policy, broken custom dialog | `a11y_interaction_evidence.json` and browser fixture definitions | `dynamic_accessibility: unobserved` in this run. | The Playwright module was unavailable, so the browser file skipped; #687 has not shipped compiled edges. Static fixture content is not browser proof. |
| Missing/invalid enhancement fallback declaration | `tests/contracts/test_enhancement_tier_evidence.py` and RFC 016 ledger | `no_javascript_browser: unobserved`, not `fail`, at the quality-composer boundary today. | Private compiler facts ship, but #724 diagnostics and #725 browser proof do not; the gate cannot fabricate their result. |
| Suppressed required finding | RFC 026 suppression taxonomy; future #888 fixture | `proof_integrity: suppressed`, overall `fail`. | No current quality-report implementation exists, so this negative report remains a planned #888 assertion. |

Focused proof executed for this decision:

- `examples/standalone/nojs_floor`: 9 passed;
- accessibility/enhancement evidence selection: 10 passed, with the entire
  Playwright module skipped because `playwright.sync_api` is not installed; and
- deploy/security selection: 45 passed.

These results validate the existing evidence owners. They do not satisfy the
missing clean-app or real-browser acceptance evidence.

## 6. Human-review boundary

Machines may prove wiring, status codes, rendered output, observed transitions,
DOM/focus facts, and known security configuration. V1 explicitly does not
claim to prove:

- aesthetic quality or visual distinctiveness;
- content truth, provenance, ethics, or product value;
- arbitrary business-logic correctness outside declared task assertions;
- usability for every person or assistive technology;
- WCAG conformance or legal accessibility compliance;
- performance, capacity, cost, or latency without a separately pinned
  measurement plan; or
- absence of every security vulnerability.

The human checklist may report concerns in those areas, but the quality report
must label the conclusions as human review. It cannot market them as framework
certification. A completed checklist is required for launch because agent-built
software still needs accountable ownership; it does not convert subjective
judgment into a Chirp guarantee.

## 7. Compatibility analysis

This decision composes existing evidence without changing it:

- no existing `app.check()` category, severity, default, warning policy, exit
  code, or JSON shape changes;
- no warning is silently promoted inside Chirp;
- no private compiler graph becomes public;
- no template declaration, return type, AppConfig field, CLI option,
  environment variable, scaffold, or runtime dependency is added;
- no network or Playwright dependency enters ordinary core tests; and
- no example is modified to satisfy the draft profile.

The stricter “warnings block an earned receipt” rule belongs only to the future
quality composer. Applications not requesting this receipt retain all current
behavior. A future public gate or serialization would require its own
compatibility, release, docs, and changelog review.

## 8. Fixture and canary plan for #888

1. Build one repository-owned clean app that exercises full-page and htmx
   success, invalid forms, JavaScript-disabled fallback, dynamic focus/live
   behavior, transition coverage, and production security in one app revision.
2. Derive one broken variant per dimension by changing only the owned fact;
   retain the clean app as a zero-false-failure canary.
3. Consume one authoritative result per owner; do not rescan application source
   in the quality composer.
4. Assert exact status derivation for errors, warnings, claim-relevant INFO,
   missing evidence, skipped browsers, suppressions, valid not-applicable cases,
   and pending human review.
5. Run JavaScript-enabled and disabled Playwright lanes, with browser absence
   producing `unobserved` rather than skip-as-pass.
6. Correlate required transition IDs and modes by set inclusion, not a coverage
   percentage.
7. Seed security, a11y, no-JS, broken target, invalid-form, suppression,
   redaction, and missing-artifact variants.
8. Run Lucky Cat, Forum Shell, no-JS Floor, and the new clean app as maintained
   canaries; classify every false result before changing any owner.
9. Require deterministic serialization and content-addressed evidence under
   RFC 026.
10. Keep Agent Skill and launch copy blocked until a real canonical report
    passes without suppression or unknowns.

## 9. Rejected alternatives

### Aggregate quality score

Rejected because a high average can conceal a security failure, inaccessible
interaction, missing browser run, or suppression. The report is dimensional and
the launch boundary is categorical.

### Treat all `app.check()` warnings as new errors

Rejected because this issue has no authority to change severities/defaults and
existing categories have different false-positive boundaries. The optional
earned profile can refuse unresolved warnings without modifying Chirp behavior.

### Infer browser coverage from static edges or TestClient

Rejected because neither observes actual DOM replacement, focus, history,
JavaScript-disabled behavior, or browser transport failure.

### Allow signed waivers to appear clean

Rejected because a waiver is useful governance evidence but not proof. It
remains `suppressed` and blocks the v1 earned receipt.

### Claim WCAG conformance from accessibility checks

Rejected because current rules cover bounded literal and proposed interaction
facts only. Browser automation, axe, assistive-technology testing, and human
review still cannot make a blanket legal/conformance claim here.

### Add performance or scalability claims

Rejected until a separately approved workload, environment, metric, budget,
variance policy, and reproducible measurement receipt exist. V1 records no
performance pass/fail dimension.

### Grade aesthetics, ethics, truth, or arbitrary business logic

Rejected as outside Chirp's provable contract. Human review may surface
concerns; the framework must not emit a false certification.

### Publish a CLI flag or AppConfig profile now

Rejected. The evidence categories and clean canary are incomplete, and #888 can
implement an internal composition proof before any public surface is designed.

## 10. Sign-off and blocked acceptance

The live #887 issue currently contains no recorded contract, security, or
accessibility sign-off. The required sign-offs are intentionally separate:

| Steward | Required review | Status |
| --- | --- | --- |
| contracts | Authority boundaries, warning/suppression policy, no duplicate scanner, severity non-impact | pending |
| security | Production-posture versus runtime-journey boundary; no certification overclaim | pending |
| accessibility | Static/dynamic/browser/human boundaries; no WCAG claim; #687 dependency | pending |

The following evidence blockers prevent accepting this RFC as a completed
quality contract:

1. #687 has not shipped the accepted dynamic accessibility edges.
2. #724 has not shipped enhancement-tier diagnostics.
3. #725 has not produced the required JavaScript-disabled browser proof.
4. The current environment cannot execute the existing accessibility
   Playwright fixture because Playwright is not installed.
5. No inspected maintained app is clean across the proposed required
   dimensions.
6. The three affected steward sign-offs are pending.

The decision is otherwise bounded enough for review, but issue #888 must not
implement or advertise a passing gate until these blockers clear.

**No-behavior-change receipt:** This RFC and its proposed internal schema/fixture
add no public API, CLI behavior, AppConfig field, protocol shape, contract
category, severity/default, deploy gate, template syntax, return type, runtime
dependency, scaffold behavior, example behavior, generated site output, WCAG
claim, performance claim, aggregate score, aesthetic judgment, or
business-logic certification.

**Acceptance #887:** blocked — required clean maintained-app evidence,
JavaScript-enabled/disabled browser evidence, dynamic accessibility and
enhancement sources, and contract/security/accessibility sign-offs are not yet
available.

## 11. Related work

- [RFC 015: Structured Application Inspection](015-structured-app-inspection.md)
- [RFC 016: Enhancement Tiers](016-enhancement-tier-contracts.md)
- [RFC 017: Accessibility Interaction Contracts](017-accessibility-interaction-contracts.md)
- [RFC 026: Coding-Agent Evaluation Contract](026-agent-buildability-evaluation-contract.md)
- [Issue #687: dynamic accessibility edges](https://github.com/lbliii/chirp/issues/687)
- [Issue #724: enhancement diagnostics](https://github.com/lbliii/chirp/issues/724)
- [Issue #725: JavaScript-disabled browser proof](https://github.com/lbliii/chirp/issues/725)
- [Issue #888: quality report integration](https://github.com/lbliii/chirp/issues/888)
