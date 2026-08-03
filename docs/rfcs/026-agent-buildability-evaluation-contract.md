# RFC 026: Coding-Agent Construction and Handoff Evaluation Contract

**Status:** Accepted decision collateral; no runner or framework behavior implemented

**Issue:** [#889](https://github.com/lbliii/chirp/issues/889)

**Parent epic:** [#877](https://github.com/lbliii/chirp/issues/877)

**Parent saga:** [#876](https://github.com/lbliii/chirp/issues/876)

**Schema:** `agent-buildability-eval-v1` (proposed, repository-internal)

**Created:** 2026-08-03

## Summary

Chirp will evaluate coding-agent construction and handoff through reproducible,
content-addressed evidence rather than a demo, prose judgment, or aggregate
score. A task packet fixes the requested outcome, public context, permissions,
environment, required checks, and artifacts. A run receipt records the executor
lane, events, human interventions, repairs, suppressions, failures, redaction,
and reproducibility result. A handoff run additionally proves that the second
agent received no original conversation and can account for topology changes
without leaving obsolete surfaces.

This RFC freezes the minimum v1 contract for implementing issue #890. It does
not implement a runner, select a model provider, publish a CLI or Python API,
change framework behavior, or approve an agent-buildability score or claim.
The JSON Schema and traces beside this RFC are proposed internal decision
collateral. They are not a public compatibility surface or product receipts.

## 1. Why a contract is required

A generated application can look convincing while depending on private
instructions, undeclared cleanup, cherry-picked attempts, disabled checks, or
an unrepeatable environment. Model output also varies even when Chirp does not.
Without a frozen evaluation boundary, a successful run cannot distinguish
framework strength from prompt tuning or operator intervention.

The evaluation therefore separates three authorities:

1. **The task packet** defines what was requested and what the agent could see
   or do.
2. **Deterministic evidence** records what the resulting application actually
   does under Chirp checks, tests, browser scenarios, artifact-integrity checks,
   and task assertions.
3. **The run receipt** records how the result was produced, including all human
   intervention and optional model-lane metadata.

No authority may be reconstructed from model prose. A model saying that tests
passed, a human saying that a run was clean, or a polished final answer is not
evidence without the corresponding captured artifact.

## 2. Decision

### 2.1 Evaluation unit

One evaluation unit is a versioned task packet plus one run receipt. A run is
either:

- `construction`: a fresh executor builds an application from the pinned
  starting state and public context; or
- `handoff`: an independent executor modifies a recorded construction output
  without receiving the original conversation or private maintainer notes.

Each attempt gets a distinct `run_id`. Retrying is not continuation by default;
the new receipt identifies repeated run IDs and the operator reports all
attempts selected for a published comparison. Resuming an interrupted process
may retain the same run ID only when the event log and artifact store are
append-only and the interruption is recorded.

### 2.2 What the agent receives

The agent receives only the material enumerated by the task packet:

- the exact task text whose digest is recorded;
- a pinned repository starting revision or generated scaffold artifact;
- explicitly listed public documentation, examples, and shipped tool help;
- repository instruction files available in the checked-out tree;
- the declared tool set, write roots, network policy, and command budget; and
- deterministic fixture credentials or services that contain no production
  data.

`public_only` must be true for a receipt used in product proof. Unpublished API
notes, maintainer hints, prior private conversations, hidden patches, and
unreleased commands are prohibited. The context bundle lists and hashes each
entry, allowing another operator to reconstruct exactly what was available.

This contract does not standardize one universal prompt. Each task packet owns
its exact task text. Operators may compare alternative presentation styles only
as distinct, fully captured packet versions.

### 2.3 Environment and permissions

The receipt pins repository revision, platform, Python version, Chirp revision,
dependency lock digest, locale, and timezone. The task packet pins services and
fixture data separately. Model credentials are operator inputs and are never
captured.

The permission record is deny-by-default:

- allowed tools and write roots are enumerated;
- network is `denied`, `allowlisted`, or `unrestricted`;
- an allowlist is required when network is `allowlisted`; and
- any runtime permission expansion is a material human intervention.

Ordinary deterministic validation must run with network denied and without
model credentials. A live lane may require network access to its executor, but
the application checks themselves remain reproducible offline.

### 2.4 Evidence and artifacts

Artifacts are content-addressed records with a logical URI, media type,
redaction status, producer event, and SHA-256 digest. The v1 required artifact
set is:

| Run kind | Required artifacts |
| --- | --- |
| both | exact task text, context manifest, event transcript, final source tree or patch, dependency lock, contract/inspection output, test output, artifact-integrity report, redaction report |
| construction | initial source/scaffold identity and final topology or contract projection |
| handoff | source construction receipt, change request, topology explanation, before/after topology or contract diff, obsolete-surface assertion, regression evidence |

Browser, no-JavaScript, accessibility, security, and deploy-posture evidence
become required when the task packet names those quality checks. A missing
required artifact fails the run; it cannot be replaced by an agent summary.

Artifact URIs are logical and relocatable. Absolute local paths, raw prompts
containing credentials, database contents, request bodies, cookies, and user
data are forbidden. A published receipt contains redacted artifacts or hashes
and access instructions for artifacts that cannot safely be published.

### 2.5 Event and intervention accounting

The event log is ordered by an integer sequence and records the actor, event
kind, bounded summary, optional command/exit status, referenced artifacts, and
linked intervention. Wall-clock timestamps are not required because they harm
determinism and do not establish correctness; duration may live in a separate
non-normative operator report.

A **human intervention** is any human-originated information or mutation after
the run begins that could affect the outcome. The v1 taxonomy is:

- `instruction`: clarification, hint, diagnosis, or new task information;
- `implementation`: human-authored code or application content;
- `edit`: manual mutation, cleanup, or conflict resolution;
- `environment`: permission, dependency, service, or fixture change;
- `credential`: credential delivery or refresh without substantive guidance;
- `retry_selection`: discarding, restarting, or selecting an attempt; and
- `other`: anything material not captured above.

Every intervention is recorded whether allowed or not. Pure observation that
does not reach the executor is not an intervention, but selecting which result
to publish is. Automated harness actions declared by the task packet are
`harness` events, not human interventions. Undeclared interventions fail a
product-proof run. Declared credential refresh may be non-material if it does
not change permissions, context, or application state.

### 2.6 Repair and suppression accounting

A repair record connects known failures and Chirp finding IDs to one or more
events and an iteration number. Its outcome is:

- `repaired`: deterministic evidence demonstrates that the failure is gone and
  unrelated required checks still pass;
- `failed`: the attempted repair did not converge; or
- `bypassed`: the apparent failure disappeared through suppression, weakened
  assertions, fake declarations, duplicate rendering, removal of required
  behavior, or another non-repair.

The task packet sets a repair-iteration bound per scenario. Exceeding it does
not erase the trace; the run fails or remains incomplete with a classified gap.
Exact model wording is never graded.

All suppressions, ignores, warning-policy changes, expected-failure markers,
coverage exclusions, and check removals are recorded. A required finding may
only be suppressed when the task packet explicitly approves the mechanism and
rationale. Disabling a required check, weakening its assertion, or creating a
parallel view to avoid a contract never counts as convergence.

### 2.7 Handoff independence

A handoff receipt must:

- cite the source construction run and its receipt digest;
- record a true context reset;
- set `original_conversation_provided` to false;
- hash the exact new change request;
- capture the second agent's topology explanation before implementation;
- capture before/after topology or contract-diff evidence; and
- identify a deterministic obsolete-surface check.

The second agent may use the repository, its public instructions, and the same
public Chirp surfaces allowed by the task packet. It may not receive the first
agent's conversation, scratch notes, private explanation, or an unrecorded
maintainer walkthrough. A cosmetic-only change cannot satisfy a handoff packet.

### 2.8 Model independence and variance

Correctness belongs to deterministic checks, not to a model identity. A lane
records whether it is `deterministic` or `live_model`, plus bounded provider,
model, revision, parameters digest, and attempt metadata when applicable.
Provider credentials, hidden system prompts, and chain-of-thought are never
recorded.

Model comparisons require the same task-packet version, starting revision,
context bundle, permissions, and deterministic check set. Differences are
reported as per-run outcomes and variance notes, never averaged into a claim
that Chirp passed. At least two independent live lanes are required by later
canonical construction proof, but ordinary CI validates schemas, fixtures,
replays, and deterministic checks without a live model.

Changing the model or sampling parameters creates a new lane, not a transparent
resume. A comparison must retain failed and incomplete lanes; cherry-picking a
successful attempt is a recorded `retry_selection` intervention and invalidates
an independent product-proof claim unless the comparison policy explicitly
includes every attempt.

## 3. Pass, fail, and ownership boundaries

`result.status` has three values:

- `pass`: every required task assertion and deterministic check passed; every
  required artifact is present and integrity-checked; no undeclared
  intervention or invalid suppression occurred; and handoff independence holds
  when applicable;
- `fail`: a required assertion/check failed, a required artifact is missing,
  an intervention/suppression boundary was violated, a repair was bypassed, or
  the task exceeded its accepted limits; or
- `incomplete`: execution stopped before a decision could be reached, including
  infrastructure interruption without enough evidence to assign a failure.

No weighted score can override a failure. Performance, token use, duration,
and repair count may be reported as descriptive measurements only after the
pass/fail boundary is evaluated.

Every failure has one primary classification and owner:

| Failure class | Owner rule |
| --- | --- |
| `framework` | A documented public Chirp surface is incorrect, internally inconsistent, nondeterministic, or lacks the evidence needed to diagnose a framework-visible failure. |
| `task` | The packet is ambiguous, internally inconsistent, impossible from its allowed context, or asserts behavior outside its stated scope. |
| `executor` | The agent ignores available instructions/evidence or produces incorrect application logic while Chirp's declared surface behaves as documented. |
| `environment` | Platform, dependency, fixture, credential, or service state prevents a valid run without demonstrating a Chirp defect. |
| `harness` | Capture, replay, redaction, integrity, or orchestration infrastructure is wrong. |
| `nondeterminism` | Repeated equivalent deterministic evidence disagrees and the source is not yet isolated. |
| `privacy` | Required evidence cannot be safely retained or published under the redaction policy. |

Uncertain ownership is `unclassified`, causes `incomplete` or `fail`, and must
be investigated rather than charged to Chirp or the model by impression. A
repeated framework-owned gap becomes a focused Chirp issue. A task-owned gap
requires a packet revision and invalidates comparisons across the old and new
versions.

## 4. Proposed `agent-buildability-eval-v1` receipt

The adjacent
[`026-agent-buildability-eval-v1.schema.json`](026-agent-buildability-eval-v1.schema.json)
is the complete proposed Draft 2020-12 JSON Schema. It is strict
(`additionalProperties: false`), uses explicit version identity, and contains
no runtime payload or public Chirp type. The following tables map every field
to its producer and first consumer or planned #890 assertion. Fields listed in
one row share that producer and assertion.

### 4.1 Run identity and input fields

| Fields | Producer | Consumer / planned assertion |
| --- | --- | --- |
| `schema_version` | runner serializer | exact `agent-buildability-eval-v1`; reject unknown major |
| `run_id`, `run_kind` | run initializer | uniqueness; construction/handoff conditional validation |
| `task.id`, `task.version` | task packet | locate immutable task definition; comparison equality |
| `task.packet_sha256`, `task.objective_sha256` | packet materializer | packet and exact task-text integrity |
| `environment.repository_revision`, `environment.chirp_revision` | clean-workspace setup | checkout identity and rerun equality |
| `environment.platform`, `environment.python_version` | environment probe | supported-lane description; comparison grouping |
| `environment.dependency_lock_sha256` | lock capture | dependency integrity and offline replay input |
| `environment.locale`, `environment.timezone` | environment probe | deterministic locale/time assertion |
| `lane.id`, `lane.executor_kind`, `lane.attempt` | lane initializer | lane identity; retain all attempts |
| `lane.provider`, `lane.model`, `lane.model_revision`, `lane.parameters_sha256` | optional live adapter | redact credentials; model-variance grouping; null for deterministic lanes |
| `context.public_only`, `context.prior_conversation`, `context.private_instructions` | context assembler/operator attestation | product-proof eligibility and handoff independence |
| `context.bundle_sha256` | context assembler | rebuild exact allowed context |
| `context.entries[].kind`, `.locator`, `.sha256` | context manifest | entry allowlist and content integrity |
| `permissions.tools`, `.write_roots`, `.network`, `.network_allowlist` | sandbox/task packet | deny undeclared capabilities and detect permission expansion |

### 4.2 Evidence, action, and classification fields

| Fields | Producer | Consumer / planned assertion |
| --- | --- | --- |
| `artifacts[].id`, `.kind`, `.uri`, `.media_type` | artifact store | uniqueness, required-kind lookup, relocatable retrieval |
| `artifacts[].sha256` | artifact store | post-redaction content integrity |
| `artifacts[].redacted` | redactor | prevent publishing unreviewed sensitive artifacts |
| `artifacts[].producer_event_id` | event recorder | provenance; null only for pre-run packet inputs |
| `events[].id`, `.sequence`, `.actor`, `.kind`, `.summary` | append-only event recorder | referential integrity, strict ordering, and bounded audit narrative |
| `events[].command`, `.exit_code` | command adapter | reproduce commands and outcomes; null for non-command events |
| `events[].artifact_ids`, `.intervention_id` | event/artifact recorders | referential integrity and intervention linkage |
| `interventions[].id`, `.kind`, `.declared`, `.summary` | operator recorder | intervention count and undeclared-intervention failure |
| `interventions[].event_id`, `.material` | event recorder/operator classification | provenance and product-proof eligibility |
| `repairs[].id`, `.failure_ids`, `.finding_ids`, `.iteration` | repair-loop observer | bound iterations and join diagnostics to attempts |
| `repairs[].event_ids`, `.outcome`, `.bypass_kind` | repair-loop observer | require post-repair proof; bypass always fails required convergence |
| `suppressions[].id`, `.mechanism`, `.location`, `.justification` | source/result scanner | enumerate every weakening mechanism with a concrete source |
| `suppressions[].required_finding`, `.disposition` | task assertion classifier | reject required or invalid suppressions; prove removals |
| `checks[].id`, `.kind`, `.status`, `.required` | deterministic validators/task packet | calculate pass boundary without model prose |
| `checks[].artifact_ids`, `.summary` | validator capture | evidence join and bounded human rendering |
| `failures[].id`, `.class`, `.owner`, `.summary`, `.artifact_ids` | classifier with operator review | route follow-up work and preserve evidence for disputed ownership |

### 4.3 Privacy, replay, handoff, and result fields

| Fields | Producer | Consumer / planned assertion |
| --- | --- | --- |
| `redaction.policy_version` | redactor configuration | policy pinning and receipt comparison |
| `redaction.secret_scan`, `.privacy_scan`, `.removed_items`, `.unresolved` | redaction validators | publication gate; unresolved privacy fails/incompletes |
| `reproducibility.offline_replay`, `.replay_of` | replay validator | prove deterministic validation without model/network; link reruns |
| `reproducibility.deterministic_checks_sha256` | task/check-set materializer | prevent silent assertion changes |
| `reproducibility.repeated_run_ids`, `.variance_notes` | comparison report | retain attempts and explain bounded model/environment variance |
| `handoff` | handoff initializer | must be null for construction and present for handoff |
| `handoff.source_run_id`, `.source_receipt_sha256` | accepted construction receipt | provenance and exact starting-state proof |
| `handoff.context_reset`, `.original_conversation_provided` | context assembler/operator attestation | require true independent context |
| `handoff.change_request_sha256` | handoff task packet | exact requested-change integrity |
| `handoff.topology_summary_artifact_id` | pre-change agent output capture | prove understanding before implementation |
| `handoff.before_graph_artifact_id`, `.after_graph_artifact_id` | inspection/diff capture | demonstrate intended topology change |
| `handoff.obsolete_surface_check_id` | task assertion | prove stale routes/templates/blocks/forms are removed |
| `result.status`, `.reasons` | final evaluator | explicit outcome and stable failure explanation |
| `result.required_checks_passed`, `.undeclared_interventions`, `.invalid_suppressions`, `.missing_artifacts` | deterministic finalizer | enforce non-negotiable pass boundaries |
| `result.framework_failure_ids` | failure classifier/finalizer | join framework-owned gaps and create focused follow-up issues |

Cross-record referential integrity, required artifact kinds, check-set equality,
repair bounds, and “all required checks passed” are runner assertions rather
than JSON Schema claims. JSON Schema validates document shape; it does not
pretend to validate referenced artifact contents or application behavior.

## 5. Task-packet outline

The implementation should represent a task packet as repository-owned data,
not a public Chirp API. The smallest packet contains:

```text
identity
  id, version, run_kind, objective file, packet digest
starting_state
  repository/scaffold revision, fixture-data digest, setup command
public_context
  exact docs/examples/help entries and context-bundle digest
permissions
  tools, write roots, network policy and allowlist
environment
  Python/platform matrix, dependency lock, locale, timezone, services
scenarios
  required journeys, intentional breakages, repair iteration bounds
assertions
  task-specific outcomes and required deterministic checks
artifacts
  required kinds, capture commands, integrity and retention policy
interventions
  allowed non-material operations; everything else declared and classified
redaction
  policy version, forbidden content classes, publishable artifact rules
handoff (handoff packets only)
  source receipt, independent-context rule, change request, obsolete surfaces
```

The packet should reference shipped commands and public documentation rather
than copying framework behavior into an evaluator-only manual. A task-specific
assertion may state the desired application behavior, but must not prescribe a
hidden implementation or expected model wording.

## 6. Contract fixtures

Two adjacent records exercise the draft schema:

- [`026-agent-buildability-construction-trace.json`](026-agent-buildability-construction-trace.json)
  covers a construction trace, declared environment intervention, a diagnosed
  block-target repair, suppression scan, deterministic checks, redaction, and
  offline replay metadata; and
- [`026-agent-buildability-handoff-trace.json`](026-agent-buildability-handoff-trace.json)
  covers independent context, source-receipt provenance, a pre-change topology
  explanation, graph diff, obsolete-surface assertion, and a classified failed
  repair.

Both records intentionally end with `status: incomplete`. They are contract
fixtures created to validate fields and classifications, not execution
receipts, benchmarks, model comparisons, compatibility promises, or evidence
that Chirp has earned an agent-buildability claim. Issue #890 must replace
fixture URIs with content-addressed captured artifacts and add referential and
integrity validation.

## 7. Risk matrix

| Risk | Failure mode | Required mitigation | Proof before canonical runs |
| --- | --- | --- | --- |
| Privacy | transcripts or artifacts retain secrets, PII, paths, cookies, or application data | post-capture redaction, secret/privacy scans, logical URIs, unresolved-publication gate | seeded-secret and path-redaction fixtures; manual sample audit |
| Cost | unbounded retries or tool/model use makes evaluation impractical | packet budgets, attempt accounting, no live lane in ordinary CI, descriptive cost reporting | budget-exhaustion fixture and retained failed attempt |
| Model nondeterminism | equivalent runs diverge or a selected success hides failures | distinct lane/attempt IDs, same deterministic check set, all-attempt retention, variance notes | repeated lanes plus an intentionally divergent fixture |
| Failure misclassification | framework, task, executor, environment, or harness is blamed by impression | evidence-linked primary class/owner, `unclassified` fallback, operator review | classification fixtures with disputed and unknown ownership |
| Prompt leakage | private instructions or original conversation make the task easier | content manifest, `public_only`, handoff context reset, exact task digest | negative fixture rejected for private context |
| Evidence spoofing | model prose or edited logs stand in for executed checks | harness-produced artifacts, SHA-256, producer-event links, integrity check | tampered artifact and missing producer tests |
| Suppression gaming | checks are disabled or assertions weakened to obtain green output | suppression inventory, check-set digest, invalid-suppression hard failure | suppression, xfail, warning-policy, and deleted-test fixtures |
| Architectural bypass | duplicate view/state/config avoids the named broken edge | task-specific anti-duplication assertions and graph/contract diff | intentional parallel-view fixture after #884/#885 |
| Schema overreach | internal evaluation schema becomes an accidental Chirp API | repository-internal status, no import/CLI/AppConfig exposure, explicit separate review for publication | public API/import/CLI snapshots remain unchanged |
| Stale task packet | framework evolves while old expected behavior remains frozen | packet version and source revision, task-owned failure classification, no cross-version comparison | incompatible packet-version fixture |

## 8. Implementation test plan for #890

### Schema and identity

1. Validate the schema itself under JSON Schema Draft 2020-12.
2. Validate construction and handoff receipts, including their conditional
   `handoff` rules and strict unknown-field rejection.
3. Reject unknown schema versions, malformed digests, duplicate IDs, dangling
   references, and mismatched task/check-set digests.
4. Preserve old v1 fixtures byte-for-byte when adding internal implementation
   fields; change the schema version for incompatible receipt changes.

### Deterministic capture and replay

1. Create a clean workspace from a pinned starting revision and lock digest.
2. Capture append-only events, commands, exit status, artifacts, producer links,
   and interruption/resume boundaries.
3. Replay all deterministic checks offline without model credentials.
4. Detect artifact tampering, missing files, silent check-set changes, and a
   resume that overwrites prior events.
5. Prove that task, context, dependency, and deterministic-check digests are
   stable across equivalent clean-clone runs.

### Intervention, repair, and suppression

1. Exercise every intervention taxonomy value and distinguish declared
   non-material credential refresh from material context/permission changes.
2. Exercise repaired, failed, and bypassed outcomes with bounded iterations and
   evidence-linked Chirp finding IDs.
3. Detect check suppression, warning-policy weakening, expected-failure markers,
   deleted assertions, fake declarations, and duplicate render sources.
4. Reject a pass with an undeclared intervention, invalid suppression, bypassed
   required repair, missing required artifact, or failed required check.

### Redaction and publication

1. Seed tokens, credentials, absolute paths, email-like PII, cookies, and
   request data across text and structured artifacts.
2. Prove post-redaction digests, redacted flags, counts, and an unresolved-item
   publication failure.
3. Keep model credentials and hidden system prompts out of receipt memory and
   disk, not merely out of final rendering.

### Model lanes and handoff

1. Run deterministic validation with no live adapter installed.
2. Gate live execution explicitly and record provider/model/revision/parameter
   metadata without secrets or chain-of-thought.
3. Retain successful, failed, interrupted, and restarted attempts in comparison.
4. Reject a handoff with original conversation, missing context reset, changed
   source receipt, missing pre-change topology explanation, or no obsolete-edge
   assertion.
5. Run at least two live lanes only in explicitly gated proof jobs; compare
   deterministic outcomes without an aggregate score.

## 9. Rejected alternatives

### Grade the final source tree only

Rejected because it cannot reveal hidden human implementation, cherry-picked
attempts, prompt leakage, or a repair achieved by disabling checks.

### Standardize one canonical prompt

Rejected because prompt wording would become an accidental compatibility
surface and overfit a changing model. Exact task text is versioned per packet;
comparisons use the same packet.

### Require one model vendor or provider SDK

Rejected because Chirp correctness must not depend on a vendor, credential, or
network service. Live adapters remain optional evaluation infrastructure.

### Put the runner in Chirp's public CLI or runtime

Rejected for v1. A repository tool can prove the contract without adding a
public command, import, AppConfig field, runtime dependency, or support burden.
Any later publication requires separate API and compatibility review.

### Produce a weighted quality or agent score

Rejected because weights can hide failed security, correctness, accessibility,
or intervention boundaries. V1 reports categorical pass/fail/incomplete plus
descriptive measurements.

### Record full chain-of-thought

Rejected because it is neither required for reproducibility nor appropriate
evidence. Capture task inputs, tool/event transcripts, bounded summaries, code,
and deterministic outputs.

### Let a maintainer silently clean the result

Rejected because it destroys the construction and handoff claim. Human edits
are material interventions and remain visible even when they improve the app.

### Treat every agent mistake as a Chirp failure

Rejected because business-logic mistakes and ignored instructions can occur
while the framework behaves correctly. Ownership follows the evidence-based
classification boundary in section 3.

## 10. Delivery boundaries and collateral

Issue #890 may implement repository-owned evaluation tooling and fixtures from
this contract. It must not infer authorization for:

- model or provider dependencies in Chirp core;
- network access in ordinary CI;
- a public `chirp` command, Python import, AppConfig field, or serialized
  framework inspection profile;
- a universal prompt, auto-fixer, source mutation outside the evaluated agent,
  leaderboard, or product claim; or
- changes to return types, named-block rendering, contract severity, or runtime
  behavior.

The runner may consume existing public commands, test helpers, inspection
output, contract diffs, and browser evidence. Proposed public inspection work
remains governed by RFC 015 and RFC 021; this evaluation contract does not
publish their private compiler models.

Documentation impact is limited to this RFC and its decision fixtures. No site,
README, example, scaffold, public API, or changelog update is warranted until
implementation ships or a product claim is independently earned.

**No-public-API receipt:** This decision adds no public Python name, CLI command
or option, AppConfig field, protocol shape, runtime dependency, contract
category or severity, scaffold behavior, environment variable, HTTP route, or
supported serialization. `agent-buildability-eval-v1` is proposed internal
repository tooling collateral and has no compatibility guarantee before #890
implements and separately reviews it.

**Acceptance #889:** n/a (decision collateral only; behavioral proof belongs to
#890/#894).

## 11. Related work

- [RFC 008: Internal Hypermedia Program](008-internal-hypermedia-program.md)
- [RFC 015: Structured Application Inspection](015-structured-app-inspection.md)
- [RFC 021: Contract Explorer](021-contract-explorer.md)
- [Hypermedia Application Compiler](../hypermedia-application-compiler.md)
- [Issue #890: evaluation runner and fixtures](https://github.com/lbliii/chirp/issues/890)
- [Issue #891: repair convergence](https://github.com/lbliii/chirp/issues/891)
- [Issue #892: canonical construction receipt](https://github.com/lbliii/chirp/issues/892)
- [Issue #893: independent handoff receipt](https://github.com/lbliii/chirp/issues/893)
