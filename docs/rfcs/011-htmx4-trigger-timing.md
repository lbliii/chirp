# RFC 011: htmx 4 Trigger Timing

**Status:** Draft — implementation requires maintainer acceptance

**Issue:** [#549](https://github.com/lbliii/chirp/issues/549)

**Upstream previews:** htmx `2.0.10`, commit
[`bdc7d7d3`](https://github.com/bigskysoftware/htmx/commit/bdc7d7d3e25d0390c7ee11049806e8279b075598),
and htmx `4.0.0-beta5`, commit
[`5300af9e`](https://github.com/bigskysoftware/htmx/commit/5300af9e7af8b196f9fbf806cab79a5780b62291)

## Summary

Chirp will not silently translate `HX-Trigger-After-Swap` or
`HX-Trigger-After-Settle` to `HX-Trigger` or to htmx 4's
`htmx:after:swap`. Those translations lose the timing contract encoded by the
public helpers. The helpers remain valid htmx 2 response builders while that
client tier is supported. An explicitly provisioned htmx 4 request that
receives either removed header will fail loudly with migration guidance.

htmx 4 applications should use its per-target lifecycle events instead:
`htmx:before:settle` is the first public hook after a target's DOM mutation,
and `htmx:after:settle` is the post-settle hook. Dynamic event data belongs in
the rendered HTML block and is read by application-owned JavaScript; Chirp
will not add a JSON response side channel or a timing emulation extension.

This RFC records a design only. It does not change current runtime behavior.

## Context

The public `Response` helpers currently preserve three meanings:

1. `HX-Trigger` fires when the response is received, before the swap;
2. `HX-Trigger-After-Swap` fires after DOM replacement and before settling;
3. `HX-Trigger-After-Settle` fires after settling.

htmx 4 removes the latter two response headers. Its beta 5 core also emits its
request-level `htmx:after:swap` only after every per-target
`htmx:after:settle` has completed. Mapping both headers to either remaining
facility would collapse distinct application behavior.

The pinned browser spike in
`tests/spikes/test_htmx4_trigger_headers_preview.py` proves the mismatch:

- htmx 2.0.10 dispatches receipt, after-swap, and after-settle events in order;
- htmx 4.0.0-beta5 dispatches `HX-Trigger` but ignores both removed headers;
- htmx 4 dispatches `htmx:after:settle` before its request-level
  `htmx:after:swap`.

## Goals

- Preserve the meaning of Chirp's three trigger phases.
- Keep payload encoding and repeated-call merging unchanged for htmx 2.
- Make htmx 4 incompatibility visible instead of silently dropping behavior.
- Give applications a CSP-safe htmx 4 migration pattern based on rendered
  HTML and public lifecycle events.
- Keep client-version detection consistent with issue #545.
- Keep testing helpers and DevTools truthful about client execution.

## Non-goals

- No new return type, `AppConfig` field, top-level export, or CLI flag.
- No JavaScript compatibility extension that reconstructs removed headers.
- No remapping to immediate `HX-Trigger`.
- No JSON API or parallel response serializer.
- No htmx 4 default flip; issue #551 owns that decision.
- No removal date for the htmx 2 helpers in this RFC.

## Inventory

The repository-wide sweep found the complete current surface:

- response builders and SSE no-op mirrors in `src/chirp/http/response.py`;
- response encoding and merge tests in `tests/test_response.py`;
- `assert_hx_trigger(..., after="swap" | "settle")` in
  `src/chirp/testing/assertions.py` and `tests/test_testing_helpers.py`;
- capture of all three headers in
  `src/chirp/server/devtools/js/collectors.js`;
- response documentation in
  `site/content/docs/build-apps/pages-navigation/request-response.md`;
- testing documentation in
  `site/content/docs/quality/testing/assertions.md`.

No Chirp example or framework runtime path calls either timing helper. A
downstream owner search found mirrored documentation but no shipped
application-code use. A separate public RFC example uses a raw timing header;
that is migration evidence, not a Chirp runtime dependency.

The global sweep for this accepted P0 was:

```console
rg -n "HX-Trigger-After-(Swap|Settle)|with_hx_trigger_after_(swap|settle)|after=.(swap|settle)." \
  src tests docs examples site README.md
```

## Decision

### 1. Preserve meanings, not unsupported bytes

`with_hx_trigger()` remains portable and continues to encode `HX-Trigger`.
The two timing helpers retain current encoding and merge behavior for htmx 2.
Their public names and payload types do not change.

For htmx 4, ignored header bytes are not a compatibility contract. Chirp will
not claim support merely because the server emitted them.

### 2. Select the client tier before applying the boundary

Issue #545 owns exact asset provisioning and version matching. This RFC relies
on that selected tier and does not infer a client from `User-Agent` or one
request header alone.

When a provisioned htmx 4 request reaches the response-writing boundary,
Chirp inspects final response headers. If either removed timing header is
present, including when set manually, the response fails before bytes are
sent. The actionable error names the unsupported header, selected version,
corresponding helper, replacement lifecycle phase, and rendered-data pattern.
The implementation should use an internal error, not a new public export.

An htmx 2 request keeps current behavior. A generic non-htmx response keeps the
literal headers because Chirp does not own its consumer. A mixed-tier
deployment combines immutable provisioning with htmx 4's `HX-Request-Type`;
the header alone is not a trusted version declaration.

### 3. Use per-target lifecycle events for htmx 4

Application JavaScript listens for:

- `htmx:before:settle` after a target's DOM mutation and before settling;
- `htmx:after:settle` after that target completes settling.

The beta 5 request-level `htmx:after:swap` occurs after per-target settling and
must not be recommended as a direct replacement.

When a server-derived payload is needed, the same Kida block renders it into a
data marker near the affected content. External application JavaScript reads
the marker at the chosen lifecycle hook, parses it without `eval`, and
dispatches the application event. Marker naming stays application-owned in
this RFC; Chirp is not standardizing a new client protocol.

This keeps dynamic data on the HTML render surface and avoids pretending that
main, OOB, and partial targets share one response-wide swap moment.

### 4. Reject a compatibility adapter

A simple adapter cannot be lossless:

- `HX-Trigger` fires before DOM mutation;
- htmx 4 `htmx:after:swap` fires after settling in beta 5;
- before/after-settle events are per task, so main, OOB, partial, delete, and
  `swap:none` work do not share one old-style response callback;
- counting or rewriting beta task objects depends on provisional internals and
  still mishandles task paths that return before lifecycle emission.

Shipping that adapter would turn a stable Python helper into a provisional
JavaScript approximation. Chirp instead exposes the incompatibility.

### 5. Keep payload encoding and merging unchanged

The response helpers continue accepting a string event name or dictionary.
Repeated calls continue merging into one JSON object exactly as today. No
payload is decoded and re-encoded merely because htmx 4 is provisioned; the
request is rejected before delivery.

`HX-Trigger` retains its current encoding and merging path. Timing migration
does not alter receipt-phase behavior.

### 6. Make testing assertions tier-explicit

`assert_hx_trigger(response, event, after="swap" | "settle")` remains a valid
wire assertion for htmx 2 and generic response construction. It proves header
encoding; it does not prove browser execution under htmx 4.

The implementation must update its docstring, assertion failure text, and
testing documentation to say so. An htmx 4 behavior test uses browser
lifecycle events and rendered data, not a positive assertion for a removed
header. Any new public test helper requires separate API approval.

### 7. DevTools reports support, not just header presence

DevTools continues collecting all three headers because their presence is
diagnostic. For a provisioned htmx 4 request, it labels the two removed headers
as unsupported and records the response failure. It must not label either as a
delivered browser event.

For htmx 2, DevTools retains the current phase names. For application-owned
htmx 4 lifecycle listeners, it records ordinary lifecycle events but does not
infer that a custom event came from a removed response header.

### 8. Cache and proxy behavior follows the selected tier

A deployment serving htmx 2 and htmx 4 clients from the same endpoint must
prevent a successful htmx 2 timing response from being replayed to htmx 4. The
implementation must audit the current htmx `Vary` policy and add
`HX-Request-Type` wherever final response behavior varies by that field.

No cache key is added at the Python response-helper layer. Exact tier
provisioning remains the primary boundary; proxy variation is defense in depth
for mixed-client deployments.

## Security, CSP, and failure consequences

- The migration listener is external application JavaScript and works with a
  no-inline-script CSP.
- Dynamic payloads are HTML-attribute escaped and parsed as data, never
  evaluated as code.
- The server does not trust `HX-Request-Type` without the provisioned tier.
- The error path does not echo unbounded response-header content.
- A removed header produces a visible failure instead of silently omitting
  required UI behavior.
- No generated adapter asset, CDN URL, or new nonce behavior is added.

## Free-threading consequences

The selected client tier is immutable runtime state from issue #545. Response
inspection uses the frozen response and request-local context. It adds no
shared mutable registry, post-freeze mutation, or lock. DevTools records remain
request-scoped under their existing lifecycle.

## Required implementation proof

The implementation PR must include:

1. Current htmx 2 response encoding and repeated-call merge tests.
2. Server tests accepting the response for provisioned htmx 2 and rejecting it
   before send for provisioned htmx 4.
3. Helper-set and manually set headers, both removed names, string and
   dictionary payloads, and mixed-case header names.
4. Explicit generic non-htmx behavior.
5. A pinned browser test proving receipt, post-mutation, and post-settle order
   with the documented htmx 4 lifecycle/data pattern.
6. OOB or partial multi-target proof that docs do not imply one global phase.
7. DevTools labeling removed headers unsupported under htmx 4.
8. An `app.check()` or provisioning diagnostic for detectable ambiguous
   client tiers.
9. Cache proof for any mixed-tier `Vary` behavior.
10. Public API notes, site/testing docs, migration guidance, and towncrier
    collateral.
11. Ruff, format, ty, focused tests, and the relevant full suite.

## Dependencies and rollout

1. Issue #545 defines exact htmx asset provisioning and version matching.
2. Maintainers accept or revise this RFC.
3. Issue #549 implements response-boundary rejection, documentation, DevTools,
   cache proof, and browser proof without changing payload encoding.
4. Issue #551 decides whether and when htmx 4 becomes the default.
5. Removing or globally deprecating the htmx 2-only helpers requires a
   separate public API decision and migration window.

## Steward signals

```text
Steward: HTTP Primitives
Area: Response trigger helpers
Severity: P0
Invariant: Public response helpers must preserve documented phase and merge semantics.
Evidence: src/chirp/http/response.py:241 -> tests/test_response.py:176
User Impact: A silent remap fires application behavior at the wrong DOM phase.
Required Fix: Keep htmx 2 encoding and reject unsupported htmx 4 delivery before send.
Required Proof: String/dict/merge tests plus version-aware server tests.
Collateral: Public API notes, site response docs, migration guide, changelog.
Confidence: High
Verification Status:
machine-verified

Steward: Server And Negotiation
Area: Client-tier response dispatch
Severity: P0
Invariant: Successful delivery must not claim behavior the selected client cannot execute.
Evidence: upstream htmx@5300af9e/src/htmx.js:654 -> upstream htmx@5300af9e/src/htmx.js:1252
User Impact: htmx 4 silently ignores both timing headers.
Required Fix: Combine immutable provisioning with request classification and fail before send.
Required Proof: htmx 2/4/generic request matrix and cache-variation tests.
Collateral: DevTools, contract diagnostics, migration docs.
Confidence: High
Verification Status:
machine-verified

Steward: Contract Checks
Area: htmx client compatibility
Severity: P1
Invariant: Detectable production-safety mismatches have actionable diagnostics.
Evidence: src/chirp/contracts/AGENTS.md:1
User Impact: Operators otherwise discover the mismatch through missing events.
Required Fix: Diagnose tier mismatch at startup where possible and at dispatch otherwise.
Required Proof: Production/debug parity and exact error-message assertions.
Collateral: Contract reference and troubleshooting guidance.
Confidence: High
Verification Status:
machine-verified

Steward: Testing Helpers
Area: assert_hx_trigger timing assertions
Severity: P1
Invariant: Assertions state whether they prove wire shape or browser behavior.
Evidence: src/chirp/testing/assertions.py:124 -> tests/test_testing_helpers.py:351
User Impact: A passing header assertion can falsely reassure an htmx 4 migration.
Required Fix: Label timing assertions as htmx 2/generic wire assertions.
Required Proof: Assertion docs/failure tests and pinned browser coverage.
Collateral: Testing docs and public API notes.
Confidence: High
Verification Status:
machine-verified

Steward: Narrative Docs
Area: Response and testing guidance
Severity: P1
Invariant: Every documented response feature traces to supported client behavior.
Evidence: site/content/docs/build-apps/pages-navigation/request-response.md:201 -> src/chirp/http/response.py:241
User Impact: Current examples become silent no-ops in htmx 4.
Required Fix: Add tier labels, lifecycle examples, and no-lossy-remap rationale.
Required Proof: Docs tests plus source and browser citations.
Collateral: Site docs, migration guide, changelog; no generated site output.
Confidence: High
Verification Status:
machine-verified
```

The HTTP and server stewards independently identify silent timing collapse as
P0, so the Convergence Rule keeps it at P0. Implementation may not close the
issue with a header rename or one-phase JavaScript shim.

## Decision log

### Accepted in this draft

- Keep helper payload encoding for htmx 2.
- Reject removed timing headers for provisioned htmx 4 requests.
- Use per-target public lifecycle events and rendered data for htmx 4.
- Keep DevTools and assertions explicit about support versus wire presence.
- Depend on issue #545 for exact version provisioning.

### Deferred to implementation

- Internal exception class and final response-boundary location.
- Exact `app.check()` rule and diagnostic code.
- Mixed-tier `Vary` changes after auditing current negotiation.
- Final migration example and application data-marker naming.

### Rejected

- Map both headers to `HX-Trigger`: fires too early.
- Map either to htmx 4 `htmx:after:swap`: fires after settle in beta 5.
- Bundle a task-counting extension: provisional and incomplete.
- Preserve ignored headers and document the limitation: not fail-loud.
- Add a JSON payload endpoint: violates the HTML render contract.

## Approval gate

Implementation changes public response semantics, the server response path,
DevTools, diagnostics, caching behavior, and documentation. The repository
constitution requires explicit maintainer approval. Acceptance should confirm
the version-aware rejection policy and per-target lifecycle/data migration
pattern before implementation starts.
