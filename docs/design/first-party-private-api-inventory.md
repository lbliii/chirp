# First-party private API inventory and ratchet

Issue [#1053](https://github.com/lbliii/chirp/issues/1053) tracks this audited
inventory. The machine-readable source is
[`scripts/private_api_ledger.json`](../../scripts/private_api_ledger.json).
Every recorded access has a classification, owning maintainer area, rationale,
follow-up or explicit no-action decision, occurrence count, and source link at
an exact Git commit. Owner fields describe responsibility; they do not claim a
GitHub assignment or a newly approved public API.

## Audited source and architecture gaps

| Application | Source revision | Production accesses / identities | Required operation and follow-up |
| --- | --- | --- | --- |
| Elbysodic | `635362f9ca9e6a358a3121bdb208b8c7018c9846` | 20 / 19 | Request-local tenant/identity/services storage and cleanup: [#1061](https://github.com/lbliii/chirp/issues/1061). Raw-query preservation, template inspection, launch configuration and worker draining: [#1056](https://github.com/lbliii/chirp/issues/1056). Legacy-password smoke retains an explicit tooling-only rationale. |
| Furatena | `63891bf0fa1782446db0725865d7c4bd15bd1dc1` | 20 / 15 | Route/template inspection, export lifespan/database/hooks/readiness, freeze-aware lazy materialization and development launch: [#1056](https://github.com/lbliii/chirp/issues/1056). |
| Showrun | `b85c4c571147905cf8b4497a2032a6a5427b6c62` | 0 / 0 | Public embed framing uses public request/response values and remains app-owned policy. Security composition may express the same policy after [#1062](https://github.com/lbliii/chirp/issues/1062); no private API migration is required by this snapshot. |
| Pidge | `47bdb846f07fe496a906717336758808734a24dd` | 1 / 1 | Narrow script origins without private middleware mutation: [#1062](https://github.com/lbliii/chirp/issues/1062). The separately recorded `PermissionError` authorization workaround is fixed by [Chirp #1063](https://github.com/lbliii/chirp/issues/1063); downstream adoption remains [Pidge #139](https://github.com/lbliii/pidge/issues/139). |
| Orrery | `c87a0cddbd2517800d36cf5049b8d1c0161dd701` | 10 / 10 | Nonce middleware without corrupting embedded JSON: [#1062](https://github.com/lbliii/chirp/issues/1062). Event-bus observation: [#1056](https://github.com/lbliii/chirp/issues/1056). Skill pending-tool inspection/wrapping and private publication stages need a bounded tools follow-up under [#1052](https://github.com/lbliii/chirp/issues/1052). |

These operations are source-backed reproductions of the coupling, not approved
API designs. In particular, Furatena's `DocsApp._shell_context` and
`DocsApp._site_base` belong to Furatena, and Elbysodic's `AppServices._database`
belongs to its service layer. The ledger records explicit no-action decisions
for these tempting false positives instead of labeling them framework defects.

The ledger also records eight statically resolved test-only accesses. The
policy permits private test inspection whether or not a particular fixture's
object type can be resolved statically. Moving inspection into production
requires a production classification; a test-only allowance cannot authorize
production code.

## Running the ratchet

Validate the ledger offline:

```sh
uv run python scripts/private_api_ratchet.py
uv run pytest tests/test_private_api_ratchet.py -q
```

Check a downstream working tree, including changes to Git-tracked source:

```sh
uv run python scripts/private_api_ratchet.py --repo elbysodic=/path/to/elbysodic
```

Multiple `--repo name=path` arguments check multiple repositories. Add `--pinned`
to require the audited Git revisions. The `Pinned first-party private API audit`
GitHub Actions workflow checks out all five source pins and runs this check
without installing or executing downstream applications. It runs on manual
dispatch and on pull requests that change the ledger, scanner, or audit workflow.
Ordinary Chirp CI validates the ledger and runs the offline fixtures; unrelated
pull requests do not fetch downstream repositories, and the audit never fetches
changing downstream default branches.

A new private symbol, a new enclosing operation, or an additional occurrence
fails with the source location, semantic identity, and instructions to add an
owner, rationale, and follow-up. Line-number-only movement does not create debt.
Removals are allowed; prune resolved allowances and update source pins during
the next audited refresh. To adopt the gate in a downstream CI, run the script
against that checkout using a reviewed Chirp tooling revision. This change does
not edit or claim to enable workflows in the five downstream repositories.

## Static boundary and review process

The scanner parses Python without importing application code. It follows Chirp
import aliases, annotated parameters and variables, constructor and local
annotated factory results, and simple aliases. Definition decorators, defaults,
annotations, class bases, and class keywords are included. Literal
`getattr`/`setattr`/`hasattr` private names and `vars(chirp_module)[name]` writes
are included. Standard dunder protocol names are not treated as private APIs.

`Any`-typed wrappers, values from application factories in other files, and
container elements require a reviewed receiver hint. Each hint specifies an
exact file/scope/receiver, a Chirp origin, and pinned source evidence. It binds
the receiver rather than permitting specific attributes, so a new private field
on that receiver still fails. Missing hinted files or renamed scopes fail and
require refreshed evidence. Application-owned objects are not inferred to be
Chirp objects simply because a variable is named `app` or `request`.

This is not whole-program type inference. Computed attribute names,
control-flow-dependent rebinding, arbitrary factory flows across modules,
runtime monkeypatching, and compatibility shims that only use public APIs need
manual source review. The initial review paired an AST candidate inventory with
searches of private runtime, request, lifecycle, skill, and CSP access and
inspected the resulting receivers and shim bodies.
The nine `manual_decisions` record compatibility shims and app-owned exclusions;
they are not an automatic detector for future semantic workarounds. Refreshing a
source pin therefore requires reviewing unresolved receiver flows and shims in
addition to running the scanner. A green ratchet proves the classified static
boundary, not exhaustive runtime independence from internals.

Consulted maps: Chirp root, public, tools, tests, docs and changelog, plus the
relevant downstream package, web, catalog, application and CLI maps. The review
protocol was applied to the inventory. Accepted findings are the operation
families above; public API design and downstream migrations are deferred to the
linked issues. No runtime behavior, scaffolds, or examples change in this task,
so those surfaces need no collateral update. No disagreement remains about the
explicit app-owned exclusions; unresolved API choices remain with their RFCs.
