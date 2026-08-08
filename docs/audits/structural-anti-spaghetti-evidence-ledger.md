# Structural anti-spaghetti evidence ledger

Decision evidence for [#883](https://github.com/lbliii/chirp/issues/883).
Parent epic [#882](https://github.com/lbliii/chirp/issues/882) · saga
[#876](https://github.com/lbliii/chirp/issues/876).

This ledger creates **no runtime behavior**. It records which structural
families Chirp can prove from compiled facts, which candidates fail the
zero-false-`ERROR` gate, and which consumers own follow-up work.

| Field | Value |
| --- | --- |
| First evidence pass | 2026-08-03 (shipped in #895 / RFC 028 draft) |
| Decision refresh | **2026-08-05** (maintainer-approved; #883 closed) |
| #884 reconcile | **2026-08-08** — no-action; empty new-predicate scope |
| Downstream Furatena execution | Unobserved (credential-gated); policy test only |

## Proven source authorities

| Source | Fact it owns |
| --- | --- |
| `src/chirp/app/hypermedia_program.py` | Frozen routes, templates, blocks, targets, declarations, origin, and stable transitions; `target_block_transitions()` supplies resolved target/block facts. |
| `src/chirp/app/hypermedia_program_compiler.py` | Deduplicates and publishes that program at application freeze. |
| `src/chirp/contracts/rules_fragment_targets.py` | Required/optional target-to-block predicate (`fragment_target_orphan` / `fragment_target_scan`). |
| `src/chirp/contracts/rules_template_declarations.py` | Explicit `declare_template` predicate (`template_declaration`). |
| `src/chirp/contracts/rules_unreachable_blocks.py` | Bounded Kida-AST composition predicate (`unreachable_block`). |
| `src/chirp/contracts/checker.py` | Static `dead` (WARNING) and `orphan` (INFO) reachability against the compiled reference set. |
| `App.override_contract_severity` / `contract_severity_overrides` | Author-declared severity policy; not a staleness oracle. |

`HypermediaProgram` remains the only topology authority. RFC 021 may project
these facts; it must not add a second scanner or infer findings from message
text.

## Candidate family survey (issue #883 scope)

Survey axes from the epic: duplicate render surfaces, ownership violations,
dead/unreachable surfaces, suppressions, and unproven declarations.

| Candidate family | Compiler / snapshot fact available today? | Positive fixture | Clean-negative / canary risk | Zero-false-`ERROR`? | Verdict |
| --- | --- | --- | --- | --- | --- |
| Required target → named block missing | Yes — `targets` + `target_block_transitions` + `required` | `tests/contracts/test_fragment_target_orphans.py` | Lucky Cat / forum_shell / scaffolds stay clean when blocks exist | Yes for required only | **Accept** (existing ERROR) |
| Optional target → named block missing | Same facts; `required=False` | same suite (optional WARNING path) | Optional absence is intentional in some layouts | ERROR would be false | **Accept** as WARNING only |
| Explicit `declare_template` / block absent | Yes — `template_declarations` + compiled template/block set | `tests/contracts/test_template_declarations.py` | Mount hoist + Lucky Cat clean when declarations match | Yes | **Accept** (existing ERROR) |
| Sibling page block outside composition roots | Bounded AST parent map + composition roots | `tests/contracts/test_unreachable_blocks.py` | Macros / layouts / intentional assembly incomplete | ERROR would be false | **Accept** as WARNING only |
| Static dead template (unreferenced) | Reference set vs template names (with `_` / package skips) | `tests/contracts/test_dead.py` | Physical aliases, runtime selection, underscore partials | ERROR would be false | **Retain** WARNING; **not** a new blocking family |
| Unreferenced route (`orphan`) | Static path references | checker orphan branch | Dynamic `url_for` / JS nav invisible | ERROR would be false | **Retain** INFO; gap projection only |
| Duplicate full/fragment response sources | No semantic-equivalence or “intended posture” fact | n/a | Multiple logical names → one physical template is intentional | No | **Reject** |
| Parallel htmx partial-tree / folder ownership | No ownership fact; RFC 025 roles are authoring guidance | n/a | Components, private partials, media alternates | No | **Reject** |
| Generic duplication / DRY / counts | Style signals only | n/a | Preference lint | No | **Reject** |
| Stale severity override / blanket suppression | Override map exists; “stale” is not proved | n/a | Deliberate app policy | No as ERROR | **Reject** as ERROR; **Accept** as visibility for #885 |
| Dynamic template/block name as dead/duplicate | Runtime names outside static reachability | n/a | False dead/duplicate claims | No | **Reject**; `declare_template` is the escape hatch |
| Structural score / deploy gate aggregate | Aggregates incomparable evidence | n/a | Masks unknowns as clean | No | **Reject** |

## Accepted high-precision families

| Family | Predicate and owning facts | Consequence | Severity | Repair | Consumer | Unknown behavior |
| --- | --- | --- | --- | --- | --- | --- |
| Target/block resolution | Compiled target has no resolved target→block transition; requiredness is a target fact | Selected response target cannot be fulfilled | Required: `ERROR`; optional: `WARNING` | Define the named block or make the target optional | `app.check()`, CLI inspection, RFC 021 projection | Dynamic runtime target construction |
| Explicit declaration validity | Declared template/block with origin is absent or unloadable | Explicit author promise is invalid | `ERROR` | Correct the declaration or define the promised surface | same | Undeclared dynamic names (not errors) |
| Conservative composition reachability | Bounded Kida AST shows sibling page block outside known roots; `extends` excluded | Block is probably unrendered | `WARNING` | Nest under a composing root or register as a real fragment target | same | Macros, layouts, intentional dynamic composition |

These three are the **complete** accepted inventory for blocking / high-precision
structural anti-spaghetti in this phase. No new `app.check()` category or
severity default is authorized by this decision.

### Related non-blocking reachability (owned for gap reporting, not new ERROR)

| Category | Default severity | Role under #885 |
| --- | --- | --- |
| `dead` | WARNING | Project as architecture debt; never promote by this RFC |
| `orphan` | INFO | Project as unproven static navigation; never ERROR here |
| `unreachable_block` | WARNING | Already accepted above; projection must not duplicate findings |

## Rejected families (documented, unimplemented as ERROR)

| Family | Why rejected | False-positive gate note |
| --- | --- | --- |
| Duplicate render surfaces / semantic markup twins | Program models declarations and edges, not semantic equivalence or intended response posture | Would ERROR on intentional aliasing and shared shells in Lucky Cat / forum |
| Component/page ownership or sibling partial-tree lint | RFC 025 roles are guidance; directories are scaffold convention | Would ERROR on legitimate components and private partials |
| Folder/component/line counts or generic duplication | Style preference, not typed hypermedia failure | Preference noise; agents learn to ignore |
| Stale suppressions / severity overrides as broken | Override may be deliberate policy; no staleness fact | Would ERROR healthy apps that demote `dead` during migration |
| Dynamic names as dead or duplicate | Outside static reachability; `declare_template` already validates promises | Would ERROR undeclared-but-valid runtime registries |
| Structural score / quality gate / deploy block | Aggregates incomplete evidence into policy | Converts unknowns and WARNINGs into false “clean” or false fail |

## Implementation owners

| Issue | Approved work | Explicitly not approved |
| --- | --- | --- |
| [#884](https://github.com/lbliii/chirp/issues/884) Detect duplicate render surfaces / ownership | **Reconciled 2026-08-08 as no-action.** Empty new-predicate scope fulfilled by documenting the rejection; optional repair-doc polish for the three accepted families only (no severity/category changes). | New `app.check()` categories; ERROR/WARNING for “duplicate surfaces” or “ownership”; second topology scanner |
| [#885](https://github.com/lbliii/chirp/issues/885) Report dead / unreachable / suppressed / unproven gaps | Inspection/projection that surfaces existing `dead` / `orphan` / `unreachable_block`, lists severity overrides as `suppressed` (never clean), and marks undeclared dynamic edges as `unproven` / `unobserved` | Promoting those to ERROR; claiming suppressions are stale; treating static reachability as behavioral coverage |

### #884 reconcile receipt (2026-08-08)

[#884](https://github.com/lbliii/chirp/issues/884) is decision-complete with **empty
new-predicate scope** per RFC 028. Shipped collateral: RFC/ledger reconcile notes
plus published repair guidance for the three accepted families
(`fragment_target_orphan` / `fragment_target_scan`, `template_declaration`,
`unreachable_block`). **Not shipped:** duplicate-surface checkers, ownership
linters, new contract categories, severity default changes, or a second
topology scanner. Reopening those rejects requires a new decision leaf.

## Reproduction and canary receipt (2026-08-05)

Passed in worktree `codex/issue-883-structural-decision` on 2026-08-05:

```console
uv run pytest \
  tests/contracts/test_fragment_target_orphans.py \
  tests/contracts/test_unreachable_blocks.py \
  tests/contracts/test_template_declarations.py \
  tests/contracts/test_dead.py \
  examples/chirpui/lucky_cat/test_app.py::TestContracts::test_app_check_passes \
  examples/chirpui/forum_shell/test_app.py::TestForumShell::test_example_app_contract_coverage_is_strong \
  tests/cli/test_scaffold_patterns.py -q
# → 77 passed (forum Kida migration warnings only)

uv run pytest tests/test_release_canary.py tests/test_mount_app.py -q
# → release canary policy + mount declaration hoist green
```

Maintained canaries exercised:

- Lucky Cat — `test_app_check_passes` (zero contract ERROR)
- forum_shell — `test_example_app_contract_coverage_is_strong` (`result.ok`)
- Scaffold patterns — `tests/cli/test_scaffold_patterns.py`
- Mounted apps — `tests/test_mount_app.py` (declaration origin hoist)

`tests/test_release_canary.py` verifies the pinned Furatena advisory workflow and
`FURATENA_CANARY_TOKEN` credential gate only. It does **not** execute the
external downstream application. Downstream remains **unobserved**.

## Zero-false-error gate (hard constraint)

An `ERROR` is permitted only when all of the following hold:

1. A compiler-owned **required promise** (required target, or explicit declaration).
2. A concrete **absence** fact in the frozen program.
3. A single deterministic **repair subject** (block name, template name, or origin).
4. Intentional **clean-negative** fixtures plus zero ERROR on Lucky Cat, forum_shell,
   and current scaffolds.

Composition reachability, dead templates, orphan routes, and suppressions fail
(1) and/or (4) for ERROR promotion. Rejected duplicate/ownership candidates fail
(1) entirely.

**Therefore:** this decision does **not** authorize any new ERROR family, any
severity default change, or any deploy gate. It does authorize classifying the
three existing high-precision families as the accepted inventory and assigning
#884/#885 as above.

## No-behavior-change receipt

Updating this ledger and RFC 028 creates no runtime rule, category, severity,
default, public API, CLI output, inspection schema, scaffold behavior, deploy
gate, or test policy.
