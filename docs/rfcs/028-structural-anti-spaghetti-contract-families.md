# RFC 028: Structural Anti-Spaghetti Contract Families

**Status:** Evidence decision; no runtime behavior change
**Issue:** [#883](https://github.com/lbliii/chirp/issues/883)
**Parent:** [#882](https://github.com/lbliii/chirp/issues/882)
**Related:** [#879](https://github.com/lbliii/chirp/issues/879), RFC 021, RFC 025
**Created:** 2026-08-03

## Decision

Chirp can prevent a specific kind of spaghetti: a typed hypermedia promise that
cannot be fulfilled by its selected named-block surface. It should only diagnose
that failure when a frozen compiler fact gives it one deterministic subject,
consequence, and repair. It must not introduce a parallel architecture scanner,
semantic markup matcher, or score.

This RFC approves no new `app.check()` family. The current inventory is the
complete evidence-backed inventory for this phase:

| Family | Predicate and owning facts | Consequence | Current / proposed severity | Repair | Consumer |
| --- | --- | --- | --- | --- | --- |
| Target/block resolution | A compiled target has no resolved target-to-block transition; requiredness is a target fact | A selected response target cannot be fulfilled | Required: `ERROR`; optional: `WARNING` / unchanged | Define the named block or deliberately make the target optional | `app.check()`, CLI inspection, private RFC 021 projection |
| Explicit declaration validity | A declared template or block, with declaration origin, is absent or unloadable in the frozen program | An explicit author promise is invalid | `ERROR` / unchanged | Correct the declaration or define the promised template/block | `app.check()`, CLI inspection, private RFC 021 projection |
| Conservative composition reachability | Bounded Kida AST composition and known roots show a sibling page block outside known composition; `extends` is excluded | The block is probably unrendered | `WARNING` / unchanged | Put it under a recognized composing page/root | `app.check()`, CLI inspection, private RFC 021 projection |

Only the first two may be errors: their subjects are explicit required promises
and their absence is proven. Composition is inherently incomplete around macros,
layouts, and intentional assembly, so it remains warning-only. Existing static
dead-template reachability likewise remains warning-only; canonical physical
aliases and runtime selection prevent a safe stronger claim.

## Rejected non-provable families

| Family | Why it is rejected |
| --- | --- |
| Duplicate render surfaces or semantically equivalent markup | The program models declarations and edges, not semantic equivalence or intended response posture. Multiple logical names may intentionally resolve to one physical template. |
| Component/page ownership or a sibling partial-tree violation | RFC 025 describes roles as authoring guidance. Directories and component categories are scaffold conventions, and no compiler fact proves authorial ownership. |
| Folder/component counts, line counts, or generic duplication | These are style signals rather than typed hypermedia failures. |
| Stale suppressions or severity overrides | An override may be deliberate application policy; current facts cannot prove it stale or unsafe. |
| Dynamic template/block names as dead or duplicate | Runtime names are outside static reachability. `declare_template` is the explicit static promise and is already validated. |
| Structural score, quality gate, or deploy block | It would aggregate incomplete, incomparable evidence into policy. |

## Evidence boundary and follow-up

The compact source, fixture, consumer, and canary evidence is retained in
[`../audits/structural-anti-spaghetti-evidence-ledger.md`](../audits/structural-anti-spaghetti-evidence-ledger.md).
`HypermediaProgram` and its compiler remain the only topology authority; RFC 021
may project those facts but must not add a second scanner or infer a finding from
message text.

The credential-gated external downstream canary is unobserved. Its advisory
workflow requires a maintainer-held token; the repository policy test is not a
downstream execution. Therefore this RFC does not claim full #883 acceptance or
authorize a new error family. A later proposal needs a new immutable compiler
fact, positive and clean-negative fixtures, available downstream evidence, and
a zero-false-`ERROR` argument before it can change behavior.

## No-behavior-change receipt

This decision creates no runtime rule, category, severity, default, public API,
CLI output, inspection schema, scaffold behavior, deploy gate, or test policy.
