# RFC 028: Structural Anti-Spaghetti Contract Families

**Status:** Decision — 2026-08-05 (maintainer-approved via [#883](https://github.com/lbliii/chirp/issues/883));
no runtime behavior change
**Issue:** [#883](https://github.com/lbliii/chirp/issues/883)
**Parent:** [#882](https://github.com/lbliii/chirp/issues/882)
**Saga:** [#876](https://github.com/lbliii/chirp/issues/876)
**Related:** [#879](https://github.com/lbliii/chirp/issues/879), [#884](https://github.com/lbliii/chirp/issues/884),
[#885](https://github.com/lbliii/chirp/issues/885), RFC 021, RFC 025
**Created:** 2026-08-03
**Decision date:** 2026-08-05
**#884 reconcile:** 2026-08-08 — closed as **no-action** (empty new-predicate
scope); optional repair-doc polish only

## Decision — 2026-08-05

Chirp prevents a specific kind of spaghetti: a typed hypermedia promise that
cannot be fulfilled by its selected named-block surface. It diagnoses that
failure only when a frozen compiler fact gives one deterministic subject,
consequence, and repair. It must not introduce a parallel architecture scanner,
semantic markup matcher, ownership linter, or aggregate score.

### Accepted families (complete inventory for this phase)

| Family | Predicate and owning facts | Consequence | Severity | Repair | Consumer |
| --- | --- | --- | --- | --- | --- |
| Target/block resolution | A compiled target has no resolved target-to-block transition; requiredness is a target fact | A selected response target cannot be fulfilled | Required: `ERROR`; optional: `WARNING` (unchanged) | Define the named block or deliberately make the target optional | `app.check()`, CLI inspection, private RFC 021 projection |
| Explicit declaration validity | A declared template or block, with declaration origin, is absent or unloadable in the frozen program | An explicit author promise is invalid | `ERROR` (unchanged) | Correct the declaration or define the promised template/block | same |
| Conservative composition reachability | Bounded Kida AST composition and known roots show a sibling page block outside known composition; `extends` is excluded | The block is probably unrendered | `WARNING` (unchanged) | Put it under a recognized composing page/root or register a real fragment target | same |

Only the first two may be errors: their subjects are explicit required promises
and their absence is proven. Composition is inherently incomplete around macros,
layouts, and intentional assembly, so it remains warning-only. Existing static
`dead` (WARNING) and `orphan` (INFO) reachability likewise remain non-blocking;
canonical physical aliases and runtime selection prevent a safe stronger claim.

This RFC approves **no new** `app.check()` family and **no severity default
change**. The three rows above are the evidence-backed inventory.

### Rejected non-provable families

| Family | Why it is rejected |
| --- | --- |
| Duplicate render surfaces or semantically equivalent markup | The program models declarations and edges, not semantic equivalence or intended response posture. Multiple logical names may intentionally resolve to one physical template. |
| Component/page ownership or a sibling partial-tree violation | RFC 025 describes roles as authoring guidance. Directories and component categories are scaffold conventions, and no compiler fact proves authorial ownership. |
| Folder/component counts, line counts, or generic duplication | These are style signals rather than typed hypermedia failures. |
| Stale suppressions or severity overrides as contract ERROR | An override may be deliberate application policy; current facts cannot prove it stale or unsafe. |
| Dynamic template/block names as dead or duplicate | Runtime names are outside static reachability. `declare_template` is the explicit static promise and is already validated. |
| Structural score, quality gate, or deploy block | It would aggregate incomplete, incomparable evidence into policy. |

### False-positive gate

Zero false `ERROR`s on Lucky Cat, forum_shell, current scaffolds, and mounted-app
declaration fixtures is a hard constraint for any proposed blocking family.
Every rejected family above fails that gate or lacks a compiler-owned required
promise. See the evidence ledger for the 2026-08-05 canary receipt.

The credential-gated Furatena downstream canary remains **unobserved**. The
repository policy test (`tests/test_release_canary.py`) is not a downstream
execution. Unobserved downstream evidence **does not** authorize new ERROR
families; it also **does not** block classifying the in-repo inventory above.

### Implementation owners

| Leaf | Decision assignment |
| --- | --- |
| [#884](https://github.com/lbliii/chirp/issues/884) | **Reconciled 2026-08-08 as no-action.** Empty new-predicate scope: no duplicate-surface or ownership checkers; no second topology scanner. Optional follow-up limited to repair-doc polish for the three accepted families (no category or severity changes). |
| [#885](https://github.com/lbliii/chirp/issues/885) | May project existing `dead` / `orphan` / `unreachable_block`, severity-override inventory as `suppressed` (never clean), and undeclared dynamic edges as `unproven` / `unobserved`. Must not promote those to ERROR or treat static reachability as behavioral coverage. |

### Leaf #884 reconcile receipt (2026-08-08)

Decision-complete: [#884](https://github.com/lbliii/chirp/issues/884) does **not**
ship new `app.check()` categories, severities, ERROR/WARNING predicates for
duplicate render surfaces or ownership, or a second topology scanner. Closure
collateral is documentation only (this RFC, the evidence ledger, and published
repair guidance for the three accepted families). A later proposal that wants
those rejected families needs a **new** decision leaf with a compiler-owned
required promise and a zero-false-`ERROR` argument — not silent work under #884.

## Evidence

Compact source, fixture, consumer, canary, and false-positive evidence lives in
[`../audits/structural-anti-spaghetti-evidence-ledger.md`](../audits/structural-anti-spaghetti-evidence-ledger.md).

`HypermediaProgram` and its compiler remain the only topology authority; RFC 021
may project those facts but must not add a second scanner or infer a finding from
message text.

A later proposal that wants a **new** error family needs a new immutable compiler
fact, positive and clean-negative fixtures, available downstream evidence or an
explicit dated waiver, and a zero-false-`ERROR` argument before it can change
behavior. That proposal is a new decision leaf — not silent work under #884/#885.

## No-behavior-change receipt

This decision creates no runtime rule, category, severity, default, public API,
CLI output, inspection schema, scaffold behavior, deploy gate, or test policy.
