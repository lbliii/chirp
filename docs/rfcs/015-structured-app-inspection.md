# RFC 015: Structured Application Inspection

**Status:** Proposed — no runtime behavior implemented
**Issue:** [#510](https://github.com/lbliii/chirp/issues/510)
**Parent epic:** [#505](https://github.com/lbliii/chirp/issues/505)
**Parent saga:** [#503](https://github.com/lbliii/chirp/issues/503)
**Created:** 2026-07-06

This RFC makes an immutable Python result the authoritative output of Chirp's
application contract inspection. Terminal text, legacy check JSON, future
versioned JSON, downstream tooling, and exit policy become projections of that
result. Merging the RFC accepts the design; it does not yet add `App.inspect()`,
change `App.check()`, alter CLI output, or publish new top-level names.

## 1. Context

Chirp already has most of the required data, but no single public composition
seam:

- `check_hypermedia_surface()` builds a mutable `CheckResult` containing typed
  `ContractIssue` values, counters, elapsed time, and `ContractCoverage`;
- `App.check()` freezes the app, runs those checks, prints terminal output, and
  raises `SystemExit(1)` according to warning policy;
- `chirp check --json` bypasses `App.check()` and independently calls
  `collect_check_json()` plus `result_to_dict()`;
- `chirp diff` consumes that minimal JSON shape and currently keys issue
  identity partly by human message text; and
- the private frozen `HypermediaProgram` has deterministic node/transition IDs
  and public-safe `SourceOrigin` values, but its dataclasses are intentionally
  not a public inspection API.

This means a downstream Python consumer either calls lower-level provisional
helpers, captures terminal output, translates `SystemExit`, or reconstructs a
partial result. It also gives terminal and JSON code paths more than one place
to decide timing, filtering, posture, ordering, and failure policy.

The design must consolidate those paths without publishing the internal graph,
breaking the frozen CLI compatibility contract, or changing contract severities
as a side effect.

## 2. Decision summary

1. Add `App.inspect(*, deploy: bool = False) -> InspectionResult` as the
   blessed non-terminal composition seam.
2. `InspectionResult`, `InspectionCounts`, and `InspectionLocation` are frozen,
   slotted provisional public types exported from `chirp`.
3. `InspectionResult.issues` is a tuple of the existing frozen
   `ContractIssue` type. `ContractIssue` gains optional keyword-only identity,
   subject, location, origin, and remediation fields without breaking current
   positional construction.
4. `App.inspect()` always returns the full discovered result, including INFO
   findings and coverage. It never accepts `warnings_as_errors`, `coverage`, or
   `include_info`; those are presentation or exit-policy choices.
5. `deploy=True` selects the existing production-posture discovery view and is
   recorded in the result. It does not mutate the app or imply an exit policy.
6. `App.check()` keeps its current signature, terminal behavior, `None` return,
   and `SystemExit(1)` contract. Internally it becomes a reporter/policy wrapper
   around `App.inspect()`.
7. Terminal output and both JSON profiles consume the same
   `InspectionResult`. Neither reruns checks nor reconstructs findings.
8. A versioned `inspection-v1` dictionary/JSON profile carries the complete
   structured result. Timing is retained on the Python result but excluded
   from deterministic serialization by default.
9. The exact `chirp check --json` top-level shape frozen by issue #571 remains
   the default legacy profile. Existing baseline files and `chirp diff` do not
   silently migrate.
10. The public result exposes opaque semantic subject IDs and copied
    public-safe locations. It never exports `HypermediaProgram`, graph node
    dataclasses, absolute paths, runtime values, template source, or request
    state.
11. Existing custom checks continue receiving the mutable `CheckResult`
    accumulator for the first increment. Chirp snapshots it once into the
    immutable public result after all checks finish.

## 3. Public Python API

### 3.1 `App.inspect()`

The accepted method shape is:

```python
class App:
    def inspect(self, *, deploy: bool = False) -> InspectionResult: ...
```

Example:

```python
from chirp import App, InspectionResult


def inspect_for_ci(app: App) -> InspectionResult:
    result = app.inspect(deploy=True)
    if not result.ok:
        for issue in result.errors:
            report_to_ci(issue.finding_id, issue.message)
    return result
```

`inspect()`:

- runs `_ensure_frozen()` and the same readiness checks as `App.check()`;
- uses the complete frozen `ContractCheckSnapshot`;
- writes nothing to stdout or stderr;
- never raises `SystemExit` for findings;
- returns clean, warning-only, and error results normally;
- preserves ordinary setup/freeze exceptions such as a configuration failure;
  and
- produces a fresh immutable result for the selected posture.

It is an inspection API, not a health endpoint. It may perform the same
template and rule work as `App.check()` and is not called on every request.

### 3.2 Public result types

The proposed shape is illustrative Python, but the field semantics are part of
this RFC:

```python
from dataclasses import dataclass
from typing import Literal

type InspectionPosture = Literal["configured", "deploy"]


@dataclass(frozen=True, slots=True)
class InspectionLocation:
    kind: str
    identifier: str
    line: int | None = None
    column: int | None = None


@dataclass(frozen=True, slots=True)
class InspectionCounts:
    routes_checked: int = 0
    templates_scanned: int = 0
    targets_found: int = 0
    hx_targets_validated: int = 0
    commandfor_validated: int = 0
    dead_templates_found: int = 0
    sse_fragments_validated: int = 0
    forms_validated: int = 0
    component_calls_validated: int = 0
    page_context_warnings: int = 0


@dataclass(frozen=True, slots=True)
class InspectionResult:
    issues: tuple[ContractIssue, ...]
    counts: InspectionCounts
    coverage: ContractCoverage
    posture: InspectionPosture
    elapsed_ms: float

    @property
    def errors(self) -> tuple[ContractIssue, ...]: ...

    @property
    def warnings(self) -> tuple[ContractIssue, ...]: ...

    @property
    def info(self) -> tuple[ContractIssue, ...]: ...

    @property
    def ok(self) -> bool: ...

    def to_dict(
        self,
        *,
        include_info: bool = False,
        include_timing: bool = False,
    ) -> dict[str, object]: ...

    def to_json(
        self,
        *,
        include_info: bool = False,
        include_timing: bool = False,
        indent: int | None = None,
    ) -> str: ...
```

`errors`, `warnings`, and `info` preserve the canonical issue order as tuples.
`ok` means “contains no ERROR finding,” exactly as today. It does not change
under warnings-as-errors policy.

`InspectionPosture` is documented as a string-literal field rather than a new
enum export. The result records `"configured"` when rules use the app's actual
configuration and `"deploy"` for the production-posture view selected by
`deploy=True`; the application's configured `env` is not copied into the
public payload.

The new classes and `App.inspect()` are provisional at introduction. They are
added to `src/chirp/__init__.py`, `docs/public-api.md`, import snapshots, and
release notes in the implementation PR.

## 4. Canonical finding model

### 4.1 Evolving `ContractIssue`

`ContractIssue` remains the one finding type. Creating a parallel
`InspectionIssue` would force check rules and consumers to translate between
two near-identical models.

The current positional fields remain in their current order:

```python
ContractIssue(severity, category, message, template=None, route=None, details=None)
```

The implementation adds optional keyword-only fields:

```python
finding_id: str | None = None
subject_id: str | None = None
location: InspectionLocation | None = None
origin: InspectionLocation | None = None
remediation: str | None = None
```

- `finding_id` identifies the semantic finding independently of message copy or
  severity. Built-in rules use a namespaced ID such as
  `form_contract:route%3APOST%3A%2Fsave:field%3Atitle:missing`.
- `subject_id` is the opaque stable ID of the compiled route, template, block,
  target, or transition involved, when one exists.
- `location` says where the problem is observed: a logical route, template,
  configuration key, plugin, or Python declaration.
- `origin` says where the compiled fact came from. It is copied from the
  internal `SourceOrigin` as scalars rather than exporting that private type.
- `remediation` is a concrete repair instruction. `details` remains supporting
  evidence, available choices, or a secondary explanation.

`template` and `route` remain supported compatibility fields. New and migrated
rules populate the richer fields in addition to them. They are not deprecated
until terminal, JSON baseline, plugin, and downstream migration evidence is
complete.

### 4.2 Stable finding identity

Built-in findings in `inspection-v1` must have a non-empty `finding_id`.
Identity inputs are semantic and public-safe:

- stable rule/category name;
- `subject_id` where a compiled subject exists;
- logical location identifier where no graph subject exists; and
- a rule-owned instance key such as field name, missing block, or conflicting
  registration.

Severity, message text, remediation wording, elapsed time, absolute paths,
registration order, object identity, and hash randomization do not participate.
Two findings in one result may not share a `finding_id`; finalization raises an
actionable framework error naming both producers if they do.

During migration, a legacy issue without an explicit identity may receive a
deterministic `legacy:` fingerprint derived from its current serialized fields.
The v1 payload marks that issue's `identity_stability` as `"message-bound"`.
Built-in rules cannot graduate the `inspection-v1` profile from preview while
such fallbacks remain. Custom plugin findings may remain message-bound without
being dropped or rewritten.

### 4.3 Subject identity without a public graph

The private compiler already builds percent-encoded semantic IDs for routes,
templates, blocks, targets, and transitions. Inspection copies only the opaque
ID string needed to correlate a finding. It does not expose:

- `HypermediaProgram` or its dataclass types;
- graph collection/query methods;
- unresolved private compiler records;
- template source text; or
- Python handler objects.

The identity string is stable within an inspection schema major version.
Changing its encoding requires a new schema version and diff migration. Issue
#511 may later use the same IDs in bounded DevTools traces and coverage, but
this RFC does not expose a graph traversal API.

### 4.4 Public-safe locations

`InspectionLocation.identifier` uses the same safety rules as compiler origins:

- handlers: `module:qualname` plus optional line;
- templates: loader-relative logical name;
- routes: method plus registered path;
- registry facts: contract/target/plugin logical name; and
- configuration: documented public field name.

Absolute filesystem paths, local usernames, source snippets, request values,
secrets, headers, cookies, form bodies, database values, and object `repr()`
output are forbidden. A column is included only when a parser has reliable
one-based source evidence.

## 5. Collection, snapshot, and free-threading lifecycle

The first implementation deliberately separates the mutable rule accumulator
from the immutable public result:

```text
frozen app state
      |
ContractCheckSnapshot
      |
private/mutable CheckResult accumulator  <-- existing custom checks append
      |
single finalization boundary
      |
frozen InspectionResult
      +--> terminal reporter
      +--> legacy JSON reporter
      +--> inspection-v1 serializer
      +--> downstream Python consumer
```

Collection runs after app freeze against one `ContractCheckSnapshot`. Once all
built-in and custom checks complete, Chirp:

1. copies the issue list to a tuple;
2. copies all counters into `InspectionCounts`;
3. retains the frozen `ContractCoverage` value;
4. validates finding uniqueness and location safety;
5. applies deterministic issue ordering;
6. records posture and elapsed time; and
7. publishes the complete `InspectionResult` once.

No registry or compiler record is mutated. No result collection is shared
between calls. No “latest inspection” global is introduced. Concurrent calls
may independently read the same frozen app snapshot and produce independent
immutable results without a new shared-state lock.

The current mutable `CheckResult` stays provisional and supported because
`ContractCheck(snapshot, result)` plugins append to it. It becomes the
collection type, not the blessed downstream read model. Changing the plugin
protocol to return findings instead of mutating an accumulator is a separate
compatibility decision.

## 6. Discovery posture and failure policy

Three concepts remain separate:

| Concept | Owner | Effect |
| --- | --- | --- |
| Discovery posture | `App.inspect(deploy=...)` | Selects normal or production-posture rule behavior and is recorded in the result |
| Presentation filtering | terminal/JSON reporter | Hides INFO or coverage from a view; never removes it from the result |
| Failure policy | caller / `App.check()` / CLI | Decides whether errors or warnings produce exit 1 |

`warnings_as_errors` must never alter severity, remove findings, or create a
second inspection run. The policy predicate is:

```python
failed = bool(result.errors) or (warnings_as_errors and bool(result.warnings))
```

`deploy=True` continues to build the existing production-posture view without
mutating `AppConfig`. It does not implicitly set warnings-as-errors in the
Python API. `chirp check --deploy` keeps its existing CLI rule that also enables
strict warnings.

## 7. Presentation architecture

### 7.1 `App.check()` compatibility

`App.check()` remains a terminal/CI convenience:

```python
def check(*, warnings_as_errors=False, coverage=False, deploy=False) -> None:
    result = self.inspect(deploy=deploy)
    print(format_inspection_result(result, show_coverage=coverage))
    if result.errors or (warnings_as_errors and result.warnings):
        raise SystemExit(1)
```

The real implementation preserves current color, fragment-registry detail,
debug behavior, output channel, newline behavior, and exception contract. The
pseudocode only shows ownership.

Debug-startup checks also consume the same final result. They may retain their
stderr output and exit behavior, but they do not call a second checker.

### 7.2 Terminal presentation

Terminal grouping, icons, colors, concern headings, timing, coverage display,
and fragment-target detail are presentation behavior. The reporter accepts an
`InspectionResult` plus display-only context. It never edits issue objects or
decides discovery posture.

Parity tests compare the IDs and counts represented by the terminal model with
the structured result. ANSI sequences, line wrapping, icons, and prose are not
serialization compatibility promises.

### 7.3 Versioned `inspection-v1` shape

`InspectionResult.to_dict()` returns this top-level shape:

```json
{
  "schema_version": 1,
  "posture": "configured",
  "ok": false,
  "info_included": false,
  "counts": {
    "errors": 1,
    "warnings": 0,
    "info": 0,
    "routes_checked": 2,
    "templates_scanned": 1,
    "targets_found": 1,
    "hx_targets_validated": 1,
    "commandfor_validated": 0,
    "dead_templates_found": 0,
    "sse_fragments_validated": 0,
    "forms_validated": 1,
    "component_calls_validated": 0,
    "page_context_warnings": 0
  },
  "coverage": {
    "post_routes": 1,
    "post_routes_with_form_contract": 1,
    "post_routes_without_form_contract": 0,
    "mounted_page_routes": 0,
    "mounted_page_routes_with_contract": 0,
    "mounted_page_routes_without_contract": 0,
    "page_shell_contracts": 1,
    "page_shell_required_blocks": 1,
    "fragment_targets_registered": 1,
    "oob_regions_registered": 0
  },
  "issues": [
    {
      "id": "form_contract:route%3APOST%3A%2Fsave:field%3Atitle:missing",
      "identity_stability": "stable",
      "severity": "error",
      "category": "form_contract",
      "message": "Required field 'title' is absent from the form.",
      "subject_id": "route:POST:%2Fsave",
      "location": {
        "kind": "template",
        "identifier": "work_items.html",
        "line": 18,
        "column": null
      },
      "origin": {
        "kind": "handler",
        "identifier": "app:create_work_item",
        "line": 42,
        "column": null
      },
      "template": "work_items.html",
      "route": "/save",
      "details": null,
      "remediation": "Add a named title control or update the form contract."
    }
  ]
}
```

The example is a schema illustration, not a claim that this exact finding
already exists.

Issue ordering is deterministic by `finding_id`. Object keys are emitted in a
documented order and `to_json()` uses JSON-native values only. `include_info`
filters the serialized view while leaving counts explicit: `counts.info`
continues to report the full result so consumers can tell that INFO findings
were omitted. The payload adds `"info_included": true|false` at top level in
the implementation schema to make that choice machine-visible.

`include_timing=False` omits volatile timing by default. When true, the payload
adds:

```json
{"timing": {"elapsed_ms": 12.345}}
```

Timing is rounded to three decimal places for transport but retained as a
float on the Python result. No timestamp, hostname, PID, working directory, or
absolute path is serialized.

### 7.4 Compatibility rules

The `inspection-v1` JSON profile is provisional at first publication:

- consumers must reject an unsupported `schema_version` rather than guess;
- adding an optional field with a safe default is allowed within v1;
- removing, renaming, changing meaning/type, or changing identity encoding
  requires v2;
- issue/category/severity changes remain public contract changes even if the
  JSON schema itself does not change; and
- stable promotion requires a downstream composition canary and one minor
  release of real baseline/diff use.

`to_json(indent=None)` is compact and deterministic. An explicit integer
indent changes whitespace only. Callers that need a dictionary use `to_dict()`
and do not parse Chirp's own JSON string.

## 8. Frozen legacy CLI and baseline compatibility

Issue #571 freezes the current `chirp check --json` success payload to exactly:

```text
ok, routes_checked, templates_scanned, issues
```

That shape remains the default after `App.inspect()` lands. The CLI runs one
inspection and feeds it into a private legacy serializer that preserves:

- exact top-level keys;
- current issue fields and INFO filtering;
- current deterministic sort behavior;
- baseline file readability;
- current `chirp diff` added/removed semantics; and
- exit 0/1 behavior and stdout/stderr routing.

The legacy serializer is not added to `chirp.__all__`. New Python consumers use
`InspectionResult.to_dict()` instead. A future CLI option to request
`inspection-v1` is a separately reviewed CLI change; it cannot silently replace
the default or reinterpret an existing baseline file.

Diff code checks profile/schema compatibility before comparing. Legacy
baselines continue using the legacy message-bound key. A future v1 diff uses
`finding_id` and reports a schema mismatch rather than treating every finding
as added/removed.

## 9. Downstream composition contract

A downstream framework or tool consumes the Python result directly:

```python
result = app.inspect(deploy=True)
payload = result.to_dict(include_info=True)

publish_findings(payload["issues"])
if result.errors:
    mark_preflight_failed()
```

The integration does not:

- capture stdout/stderr;
- catch `SystemExit` to recover findings;
- import private checker, compiler, or terminal modules;
- inspect `app._runtime_state`;
- parse terminal prose; or
- mutate issues or coverage.

The implementation proof uses a public test fixture shaped like a downstream
consumer but containing no private repository name, revision, path, or data.

## 10. Plugin extension status

The first increment does not change `ContractCheck(snapshot, result) -> None`.
Custom checks keep appending `ContractIssue` values to the mutable accumulator.
Their findings are copied into `InspectionResult` with built-in findings.

Plugin authors may populate the new keyword-only fields. Requirements:

- `finding_id` uses a package-owned namespace to avoid collisions;
- `subject_id` uses a Chirp compiled ID only when Chirp supplies it through a
  supported snapshot/helper boundary;
- locations are public-safe logical identifiers;
- remediation is concrete and contains no terminal escape sequences; and
- arbitrary plugin JSON extension objects are not supported in v1.

A plugin that omits `finding_id` remains visible with a message-bound fallback
and `identity_stability="message-bound"`. Chirp does not silently discard it or
promote its identity guarantee. Duplicate explicit IDs are errors because a
diff cannot safely choose between them.

The plugin accumulator and `ContractCheckSnapshot` remain provisional. A future
return-an-iterable protocol can be designed after real plugins adopt the
immutable result, but it is not required for downstream composition.

## 11. Error, privacy, and trust behavior

- Findings are data, not exceptions. Clean, warning, and error inspection all
  return normally.
- App freeze/readiness/configuration failures still raise their existing
  exception types; `InspectionResult` is not a wrapper for a failed app build.
- A broken custom checker continues to surface an actionable
  `plugin_check_error` ERROR rather than aborting the rest of inspection where
  current behavior supports that recovery.
- Serialization failure is fail-loud and names the unsupported field/finding;
  it never stringifies an arbitrary object with `default=str`.
- Message, details, remediation, location, and origin pass the public-safe
  filter. No secrets, request payloads, absolute paths, or object reprs enter
  the result.
- JSON is data only. Terminal escape handling stays in the terminal reporter.
- `InspectionResult` carries no callable, app, router, template environment,
  registry, database handle, or mutable metadata dictionary.

## 12. Implementation sequence

The design should land in reviewable increments:

1. Add frozen result/location/count types and the finalizer from existing
   `CheckResult`.
2. Add `App.inspect()` and prove clean/warning/error, deploy posture, timing,
   no output, no `SystemExit`, freeze, and concurrent reads.
3. Route terminal `App.check()`/debug checks through the immutable result while
   preserving byte/exit behavior.
4. Route the legacy CLI JSON/baseline/diff path through the same result without
   changing its frozen shape.
5. Add `inspection-v1` serialization and schema fixtures.
6. Migrate built-in findings to stable IDs, subjects, locations, origins, and
   remediation by rule family; keep a machine-visible count of message-bound
   fallbacks until it reaches zero.
7. Add the downstream composition fixture and public documentation.
8. Only then allow #573 and other agent surfaces to publish the structured
   result through Milo.

An implementation may use more than one PR. No PR may claim v1 stable identity
while built-in message-bound fallbacks remain.

## 13. Required proof

### 13.1 Result semantics

- clean, warning-only, ERROR, and INFO fixtures;
- every current counter and coverage field survives finalization;
- `ok`, severity tuple properties, posture, and elapsed time are correct;
- result, issue, count, coverage, and location records cannot be mutated; and
- repeated equivalent fixtures produce the same ordered IDs and default JSON.

### 13.2 Presentation parity

- terminal and both JSON profiles are generated from one mocked/spied
  inspection call;
- represented finding IDs and severity counts match the Python result;
- `coverage=False` and `include_info=False` hide presentation detail without
  changing the result;
- warnings-as-errors changes only exit status; and
- debug startup retains stderr and current failure behavior.

### 13.3 Compatibility

- the #571 subprocess test keeps the exact legacy top-level JSON keys;
- old baseline fixtures round-trip and diff without migration;
- schema/profile mismatches fail actionably;
- public import snapshots and docs agree; and
- no private graph type becomes reachable from the result.

### 13.4 Lifecycle, concurrency, and safety

- inspection before explicit freeze follows the same `_ensure_frozen()` path as
  `App.check()`;
- post-freeze app mutation remains rejected;
- concurrent inspection calls share only frozen app state and return distinct
  immutable results;
- deploy inspection does not mutate `AppConfig`;
- invalid plugin fields and duplicate IDs fail loud; and
- public-safety fixtures reject absolute paths, secrets, and non-JSON-native
  objects.

### 13.5 Downstream composition

- a consumer calls only `app.inspect()` and public result methods;
- no stdout capture, `SystemExit` translation, or private import occurs; and
- terminal, JSON, and downstream views agree on findings and counts.

## 14. Public API and collateral contract

The implementation PR updates all affected surfaces:

| Surface | Required collateral |
| --- | --- |
| App API | `App.inspect()` docs, lifecycle behavior, API tests |
| Public types | top-level lazy exports, tier table, import snapshots, type tests |
| Contract issues | keyword-only field docs, plugin compatibility, rule migration tests |
| Terminal | parity and byte/exit regression proof; no new CLI flags |
| Legacy JSON/diff | #571 shape test, old baselines, schema mismatch behavior |
| Inspection v1 | schema reference, deterministic fixtures, versioning policy |
| Compiler | opaque subject-ID mapping only; internal types stay private |
| Testing | downstream composition helper/fixture and concurrency proof |
| Docs/site | contracts guide, API reference, compiler architecture status |
| Examples/scaffolds | no default change; add only a read-only inspection example if useful |
| Release | towncrier fragment and migration note for provisional `CheckResult` consumers |

No `AppConfig` field, environment variable, mandatory dependency, return type,
render-pipeline behavior, route behavior, or scaffold default is added.

## 15. Alternatives considered

### 15.1 Return `CheckResult` directly from `App.check()` — rejected

It would still combine printing, exit policy, and composition. Existing callers
also rely on `None`/`SystemExit` behavior. A new non-terminal method is clearer
and preserves compatibility.

### 15.2 Make mutable `CheckResult` the long-term read model — rejected

Custom checks need its accumulator behavior today, but downstream consumers
should not be able to append, reorder, or change counters after publication.
The one-time immutable snapshot respects both needs.

### 15.3 Expose `HypermediaProgram` — rejected

The graph dataclasses are internal compiler implementation. Inspection needs
opaque correlation IDs and public-safe locations, not graph traversal or
renderer internals.

### 15.4 Replace `chirp check --json` with v1 immediately — rejected

Issue #571 freezes the current machine-readable shape. Silent replacement
would break baseline and automation consumers while the CLI is being migrated.

### 15.5 Put warnings-as-errors in `InspectionResult` — rejected

Strictness is caller policy. Encoding it in discovery would make identical
findings differ based on who intends to consume them.

### 15.6 Exclude INFO and coverage during collection — rejected

That creates partial results and forces a rerun for another presentation.
Filtering belongs at serialization/render time.

### 15.7 Add arbitrary plugin metadata — rejected for v1

An unbounded mapping weakens determinism, JSON safety, redaction, and schema
compatibility. Concrete extension needs should produce typed fields later.

## 16. Non-goals and not-now items

- No public compiler graph, query API, or private graph dataclass export.
- No route table or render-plan inventory beyond finding subject IDs.
- No runtime trace or transition coverage correlation; issue #511 owns it.
- No Milo/MCP/llms.txt exposure; issue #573 consumes this seam later.
- No change to contract severities, categories, rule behavior, or deploy rules.
- No new CLI flag or default JSON migration.
- No mutable metadata bag on results or findings.
- No request-time inspection cache or shared latest-result state.
- No capture of request/session/database/template-source values.
- No rewrite of the custom check protocol in the first increment.
- No REST/OpenAPI schema and no relationship to Chirp's HTML return types.

## 17. Steward synthesis

The RFC consulted the app lifecycle, contracts, CLI, docs/public API, compiler,
testing, and changelog boundaries.

### Accepted findings

```text
Steward: App Lifecycle
Area: Inspection collection and publication
Severity: P0
Invariant: Inspection reads one complete frozen app snapshot and publishes one immutable result; it never reads half-frozen state or creates shared mutable runtime state.
Evidence: src/chirp/app/AGENTS.md:18-32; src/chirp/app/state.py:289-344; src/chirp/app/hypermedia_program.py:1-21
User Impact: Half-published or mutable inspection data could differ across workers and make CI/downstream decisions nondeterministic.
Required Fix: Finalize after all checks under the existing freeze/read boundary into frozen tuples and records; keep calls independent.
Required Proof: Freeze, post-freeze mutation, deterministic publication, and concurrent inspection tests.
Collateral: App lifecycle docs, public API table, changelog.
Confidence: High
Verification Status:
machine-verified
```

```text
Steward: Contract Checks
Area: Authoritative result and finding fidelity
Severity: P0
Invariant: Severity, category, identity, location, remediation, coverage, posture, and timing survive into one authoritative result without changing rule semantics.
Evidence: src/chirp/contracts/types.py:36-108; src/chirp/contracts/checker.py:447-491; src/chirp/contracts/AGENTS.md:19-42
User Impact: Split result paths can omit findings or let terminal, JSON, and downstream tools disagree about whether an app is safe.
Required Fix: Snapshot the existing accumulator once, retain every field, and make all presentations consume that snapshot.
Required Proof: Clean/warning/error/INFO fixtures, field parity, one-run spies, and presentation comparisons.
Collateral: Contract docs, testing helpers, JSON schema reference, changelog.
Confidence: High
Verification Status:
machine-verified
```

```text
Steward: CLI And Scaffolds
Area: Frozen CLI JSON and exit behavior
Severity: P1
Invariant: `chirp check --json` keeps the #571 shape, channels, filtering, and exit policy until a separately reviewed version switch.
Evidence: src/chirp/cli/_check.py:17-82; src/chirp/cli/__init__.py:151-178; tests/cli/test_cli_compatibility_contract.py:225-242 on PR #594
User Impact: Silent schema replacement would break agent scripts and committed baselines during the Milo migration.
Required Fix: Render a private legacy profile from InspectionResult and introduce v1 programmatically first.
Required Proof: Exact-key subprocess test, legacy baseline round-trip, stdout/stderr and exit-code tests.
Collateral: CLI compatibility contract and migration note; no scaffold change.
Confidence: High
Verification Status:
machine-verified
```

```text
Steward: Compiler
Area: Stable subject identities and public boundary
Severity: P1
Invariant: Inspection may copy opaque stable IDs and safe origins but must not expose private HypermediaProgram records or a parallel graph.
Evidence: src/chirp/app/hypermedia_program.py:1-21,24-109; docs/rfcs/008-internal-hypermedia-program.md:19-33,82-96
User Impact: Publishing compiler dataclasses would freeze implementation details and invite consumers to bypass supported contract APIs.
Required Fix: Copy scalar subject IDs/locations into public finding records and keep graph access internal.
Required Proof: Public import/reachability tests and deterministic ID fixtures.
Collateral: Compiler architecture doc and inspection schema reference.
Confidence: High
Verification Status:
machine-verified
```

```text
Steward: Public API And Docs
Area: Provisional structured inspection surface
Severity: P1
Invariant: New blessed names, compatibility tier, serializer versioning, and migration expectations are documented together.
Evidence: docs/public-api.md:51-61,80-94; docs/release-policy.md:3-27; docs/AGENTS.md:18-38
User Impact: An undocumented result schema would become accidental API through downstream automation.
Required Fix: Export provisional types from chirp, document v1 and legacy profiles, and add changelog/migration collateral.
Required Proof: Import snapshots, docs contract tests, towncrier draft, and downstream fixture.
Collateral: docs/public-api.md, site API/contracts guides, changelog.
Confidence: High
Verification Status:
machine-verified
```

### Convergence

The app lifecycle and contracts stewards independently require a single frozen
snapshot-to-result publication boundary. Under the convergence rule, that
accepted invariant is P0. The contracts and CLI stewards also converge on one
authoritative result feeding every presentation; the legacy JSON adapter may
change shape only through an explicit compatibility decision.

### Minority reports

The smallest implementation would expose `check_hypermedia_surface()` as the
recommended API. That avoids a new app method, but it leaves lifecycle,
mutability, elapsed timing, posture, and future presentation ownership spread
across helpers. The RFC accepts the explicit `App.inspect()` seam.

Another view favors replacing the legacy JSON immediately so there is only one
wire profile. The compatibility contract on PR #594 shows that existing JSON is
already agent-safe and exact-key tested. The RFC keeps one canonical Python
result while temporarily supporting two deliberate serializers.

### Ranked implementation backlog

1. Immutable result/finalizer and `App.inspect()`.
2. Terminal/debug presentation migration with behavior parity.
3. Legacy JSON/baseline/diff migration with #571 compatibility proof.
4. `inspection-v1` schema and deterministic serializer.
5. Built-in stable identity/location/remediation migration by rule family.
6. Downstream composition and concurrency canaries.
7. #511 trace/coverage correlation.
8. #573 Milo/MCP/llms.txt exposure after its CLI dependency lands.

## 18. Global sweep for accepted P0s

The P0 synthesis was checked across source, tests, docs, examples, and site
content with:

```text
rg -l "app\.check\(|check_hypermedia_surface\(|collect_check_json\(|result_to_dict\(|raise SystemExit\(1\)" src tests docs examples site/content
rg -n "redirect_stdout|capture.*stdout|capsys|capfd|SystemExit" src/chirp/contracts src/chirp/app src/chirp/cli tests/contracts tests/test_cli_check.py tests/test_terminal_checks.py
```

The sweep confirmed the split at `src/chirp/app/diagnostics.py`,
`src/chirp/cli/_check.py`, `src/chirp/contracts/surface_diff.py`, and
`src/chirp/contracts/serialize.py`; tests currently assert `App.check()`
`SystemExit` and CLI capture behavior. No separate downstream-safe app method
exists. Examples mostly call `app.check()` as a pass/fail assertion, which
remains valid and needs no bulk migration.

## 19. Acceptance criteria

This design is ready to implement when reviewers agree that it:

- selects `App.inspect()` and immutable provisional public result types;
- preserves all current findings, counters, coverage, elapsed time, posture,
  stable subject identity, source origin, location, and remediation;
- keeps discovery, presentation filtering, and failure policy separate;
- makes terminal, legacy JSON, v1 JSON, and downstream Python use one result;
- preserves `App.check()` and the #571 CLI JSON/exit compatibility contract;
- versions the richer serializer and excludes volatile timing by default;
- defines plugin migration without breaking the current custom-check protocol;
- exposes no private compiler graph types or unsafe runtime/source data;
- names lifecycle, concurrency, safety, compatibility, downstream, docs, and
  changelog proof; and
- records accepted steward findings, convergence, minority views, ranked work,
  and the P0 global sweep.

Any implementation that changes the method name, public record fields, legacy
CLI shape, severity semantics, plugin protocol, or graph exposure must amend
this RFC and repeat the affected public API/steward review.
