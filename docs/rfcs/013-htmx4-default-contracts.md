# RFC 013: htmx 4 Default Contracts

**Status:** Implemented for the explicit preview lane

**Issue:** [#548](https://github.com/lbliii/chirp/issues/548)

**Upstream preview:** htmx 4.0.0-beta5 at commit 5300af9e7af8b196f9fbf806cab79a5780b62291.

## Summary

Chirp will treat the htmx 4 default changes as seven explicit framework
contracts. During preview, htmx-2-compat temporarily preserves implicit
inheritance. Chirp adopts native history refetch, main-first OOB processing,
DELETE without enclosing-form data, hx-sync queuing, and a 60-second request
timeout. Error swapping uses a deliberate hybrid: 4xx HTML swaps, while 5xx
responses do not swap unless the application explicitly scopes them.

The explicit preview implementation now ships the accepted client policy,
tier-aware diagnostics, DevTools evidence, and pinned browser proof. Htmx 2
remains the default until the separate GA release gate is satisfied.

## Decision matrix

| Surface | Preview contract | Native target | Reason |
| --- | --- | --- | --- |
| Inheritance | Temporarily restore implicit via compat | Explicit inherited modifiers | Preserve dual-version templates while dependencies are inventoried |
| 4xx errors | Swap | Swap | Validation and auth fragments are useful HTML |
| 5xx errors | Do not swap by default | Do not swap by default | Never erase a shell with an unscoped production failure |
| OOB order | Main first, then OOB/partials | Same | Updates must be independent |
| DELETE data | Exclude enclosing form | Same | Match GET-like htmx 4 semantics |
| History | Refetch, no localStorage cache | Same | Server HTML remains authoritative |
| Queue | hx-sync only | Same | Removed queue modifiers silently lose concurrency policy |
| Timeout | 60000 ms | Same | Bound stalled requests; streams use dedicated types |

## Current Chirp impact

Chirp relies heavily on inherited shell targets and selectors, currently emits
hx-disinherit on SSE boundaries, returns ValidationError as 422 HTML, renders
primary plus OOB mutations, and documents hx-delete in examples. Persistent
shell history and long-running AI/streaming paths also cross these defaults.
The current contract checker sees broad-target inheritance and OOB scope, but
does not classify htmx client tier or removed queue/DELETE semantics.

## Detailed decisions

### Inheritance: compatibility first, explicit end state

The preview manifest from #545 loads htmx-2-compat, preserving current implicit
hx-target, hx-select, hx-boost, and hx-confirm behavior. This is temporary,
not the native contract. app.check inventories inherited dependencies and
reports a migration warning with template and ancestor evidence.

Before compatibility is removed, Chirp-owned templates and applications must
either use explicit htmx 4 inherited modifiers or place attributes directly on
the consumer. Existing hx-disinherit boundaries remain meaningful only while
compatibility is active; they are removed with the migration, not ignored
early. No parallel template tree is introduced.

### Error HTML: swap 4xx, suppress 5xx

The preview config must prevent htmx-2-compat from restoring its broad 4xx/5xx
no-swap list. Chirp sets noSwap to 204, 304, and 5xx. This makes 422
ValidationError and other bounded 4xx fragments render naturally while an
unhandled 500 cannot replace a broad target or application shell.

Applications may opt a specific 5xx target into swapping with htmx 4 status
metadata only when the target is local and the returned HTML is designed for
that region. app.check rejects a 5xx swap aimed at body, a shell root, or an
unresolved selector. Debug and production use the same swap policy.

### OOB order: adopt main-first independence

Chirp adopts htmx 4 main-first behavior, followed by OOB and partial tasks in
document order. A main swap must not depend on an OOB task creating its target,
and an OOB task must not depend on main content it does not own. MutationResult,
OOB, Suspense, and shell tests prove final independence. Chirp does not reorder
rendered HTML or add a client compatibility shim.

### DELETE: explicit data inclusion

hx-delete does not include enclosing form controls. Applications that need
form data use hx-include="closest form" or place required values in the URL.
A static hx-delete inside a form with successful named controls and no include
receives a compatibility warning. If active CSRF protection depends on a form
field, the diagnostic is ERROR unless another supported token transport is
visible. Route and server method semantics do not change.

### History: refetch server HTML

Chirp adopts htmx 4 history refetch and does not restore the localStorage
history cache. Persistent shells declare one stable hx-history-elt; history
responses remain full pages from the same template/render surface so htmx can
select that region. A shell using pushed history without a stable history
element receives a warning, promoted to ERROR when a body restore could erase
registered persistent regions.

### Queuing: migrate to hx-sync

Any hx-trigger queue modifier is unsupported and app.check reports ERROR,
because silently losing request serialization can duplicate mutations. The
migration is hx-sync with an explicit selector and queue strategy. DevTools
records the resolved synchronization owner and strategy.

### Timeout: adopt 60 seconds

Chirp keeps htmx 4 defaultTimeout at 60000. Endpoints expected to outlive that
window use Stream for progressive first bytes, Suspense for deferred OOB HTML,
or EventStream for post-load SSE. An intentionally long non-streaming request
must opt out locally with hx-config timeout:0 or choose an explicit larger
bound. Chirp adds no AppConfig timeout field in this issue.

## Implementation shape

The #545 manifest carries an htmx config payload alongside its ordered scripts.
For beta5 it sets the 4xx/5xx policy and tells htmx-2-compat not to restore old
error swapping, while leaving implicit inheritance compatibility enabled.
The config is emitted as declarative metadata before deferred scripts; no eval
or application JSON response path is added.

A tier-aware htmx_compatibility contract family consumes template inventory
and the immutable manifest. New findings start at the severities stated above;
existing swap_safety and htmx_provisioned severities are not silently changed.

## Security, cache, and free-threading

Suppressing unscoped 5xx swaps prevents attacker-triggered failures from
replacing broad visible regions. DELETE diagnostics preserve CSRF transport.
History remains server-authoritative and uses normal htmx cache variation.
Client policy is immutable manifest data published at freeze; checks and
DevTools do not mutate it. No shared request queue is added server-side.

## Required implementation proof

1. Config tests for implicit compatibility, 4xx swap, 5xx suppression, and 60000 ms timeout.
2. Browser tests for local 422, broad 500, explicit inheritance migration, and compat behavior.
3. Main plus multiple OOB/partial tests proving final order independence.
4. DELETE tests with no fields, explicit hx-include, query encoding, and CSRF.
5. Back/forward refetch tests with and without hx-history-elt.
6. Queue-modifier diagnostics and hx-sync request-order browser tests.
7. TestClient contracts proving ValidationError and 500 response shape.
8. DevTools records for policy, history restore, timeout, and synchronization.
9. Public API, site, examples, scaffold audit, migration notes, and changelog.

## Dependencies, risks, minority report, and not-now

This issue depends on acceptance of #545 and feeds #546, #547, #542, #553,
and the #551 release gate. Main risks are shell wipes from 5xx HTML, hidden
inheritance dependencies, CSRF loss on DELETE, and order-coupled OOB markup.

Minority report: fully restoring htmx 2 error behavior is simpler during
preview, but it preserves the current 422 footgun and delays useful native
behavior. The hybrid 4xx/5xx policy is more explicit and safer.

Not now: a public client-policy object, an AppConfig timeout field, a second
template dialect, automatic markup rewriting, or client-side OOB reordering.

## Steward signals

Steward: Protocol And Negotiation
Area: Error response swap policy
Severity: P0
Invariant: Validation HTML remains renderable and production failures cannot erase broad targets.
Evidence: src/chirp/server/errors.py:135 -> src/chirp/templating/returns.py:376
User Impact: Wrong defaults either hide form errors or replace the shell with 500 HTML.
Required Fix: Swap 4xx, suppress 5xx, and require explicit safe 5xx targeting.
Required Proof: Browser and TestClient status/target matrix.
Collateral: Error docs, DevTools, migration guide, changelog.
Confidence: High
Verification Status:
machine-verified

Steward: Contract Checks
Area: Inheritance, DELETE, queue, history, and broad targets
Severity: P0
Invariant: Detectable silent client drift fails before production.
Evidence: src/chirp/contracts/checker.py:523 -> src/chirp/contracts/rules_swap.py:131
User Impact: Ignored queue policy, missing DELETE data, or history body swaps corrupt state/UI.
Required Fix: Add tier-aware findings without changing unrelated severities.
Required Proof: Rule matrices plus end-to-end app.check tests.
Collateral: Contract category docs.
Confidence: High
Verification Status:
machine-verified

Steward: Rendering And OOB
Area: Main-first task independence
Severity: P1
Invariant: One template produces independent main and OOB regions with fail-loud targets.
Evidence: src/chirp/templating/returns.py -> tests/contracts/test_oob_pipeline_e2e.py:235
User Impact: Order-coupled updates work in one client tier and fail in another.
Required Fix: Adopt main-first and test every typed multi-region return path.
Required Proof: MutationResult, OOB, Suspense, and shell browser coverage.
Collateral: OOB docs and examples.
Confidence: High
Verification Status:
machine-verified

Steward: Narrative Docs
Area: htmx 2/4 migration policy
Severity: P1
Invariant: Every recommended attribute and default traces to shipped behavior.
Evidence: docs/error-handling.md:105 -> site/content/docs/build-apps/html-fragments/fragments.md:155
User Impact: Copyable guidance can silently hide 422s or expose broad 500 swaps.
Required Fix: Publish the decision matrix and tier-specific migration examples.
Required Proof: Docs inventory tests and pinned browser evidence.
Collateral: Site, examples, scaffolds, public API, changelog on implementation.
Confidence: High
Verification Status:
machine-verified

The protocol and contract stewards converge on broad-target error safety as P0.

## Decision log and approval gate

Accepted in this draft: temporary implicit inheritance compatibility; native
4xx swap and 5xx suppression; main-first OOB; explicit DELETE inclusion;
history refetch; hx-sync; and a 60-second default timeout.

Rejected: broad 4xx/5xx compatibility, automatic OOB reordering, hidden DELETE
field copying, localStorage history restoration, queue shims, and no timeout.

Implementation touches client config, contract severities, shell/history markup,
examples, and documented compatibility. Maintainers must approve the complete
decision matrix before code changes begin.
