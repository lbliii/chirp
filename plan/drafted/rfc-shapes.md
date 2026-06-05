# RFC: Shapes — the verified SQL→render data contract

**Status**: Draft
**Date**: 2026-06-05
**Scope**: `src/chirp/data/`, `src/chirp/contracts/`, `src/chirp/templating/`, `src/chirp/server/`, `src/chirp/cli/`
**Related**: RFC Shared Store, RFC Contract Extensions, #143 (schema introspection), #159 (typed-SQL data layer as a contract), #162 (non-goals: no ORM)

> **The shape is the intent.** SQL in, frozen shape out — verified before you serve a byte.

---

## Problem

Chirp's data layer is deliberately *"SQL in, frozen dataclasses out. Not an ORM."* That stance is correct and we are not walking it back. But it leaves a real gap that every maturing, database-heavy Chirp app fills by hand:

- There is **no link between the data a query fetches and the fields a template renders.** A block can read `order.summary` when the query for that block never selected `summary`, and nothing notices until a user hits the page (or, worse, never — the field silently renders empty).
- Apps hand-build a **repository + frozen-row-model layer** to map SQL to view-ready shapes, then **reshape again** per page/fragment. The same shape is declared two or three times (row model, handler kwargs, template reads) with no enforcement they agree.
- **Over-fetch and N+1** are policed by convention and query-budget tests, not prevented by construction.

We validated this against [`elbysodic`](https://github.com/lbliii/elbysodic), a real ~77k-LOC database-heavy Chirp app. It is *clean and deliberate* — 0 `SELECT *`, explicit writes, query-budget regression tests, a steward forbidding template-facing SQL — and it **still** exhibits the gap:

- Its `surface_contracts` registry has **silently drifted**: it names read models `PlottingRoomView`, `NotificationInboxItem`, `PublicRealmGateway`, `NetworkHome` — **none of which exist** (the real classes are `PlottingRoomDetail`, `NotificationItem`, …). The only guard checks *tuple non-emptiness*, never field sets, so nobody noticed. This is a **live, undetected bug today.**
- A claims-directory path fires ~`2N` single-row fetches inside a per-claim-type loop, guarded only by an *absolute* 70-query ceiling with no scaled test — **unbounded as data grows.**
- The board page declares one shape **three times** (frozen composite, 18-kwarg handler spread, template reads), all hand-maintained.

The ORM's answer to all this is "navigate a mutable object graph and the database disappears" — which reintroduces hidden I/O, lazy-loading N+1, mutable tracked entities, and an identity map: the precise inverse of Chirp's frozen / explicit / stateless / no-hidden-I/O commitments, and a hazard surface under free-threaded 3.14. We want the leverage (and the admin/CRUD generation that falls out of a schema source-of-truth) **without** the ORM's stateful core.

---

## Proposal: Shapes

A **Shape** is the exact data a view declares it needs, co-located with the block that renders it. A Shape compiles to **one explicit, typed SQL query** producing a **frozen dataclass**, and `app.check()`'s **`shapecheck`** category proves at startup that the block reads only fields the query actually provides.

Data flows *toward the screen*, fetched-for-purpose, immutable — no lazy loading, no identity map, no session, no mutable tracked entities.

### The honest headline

The marquee guarantee is **not** "N+1 impossible by construction." Mature apps already bound N+1 with query-budget tests (elbysodic does). The genuinely net-new, uncontested value is the **field-level startup contract** — the thing that would have caught elbysodic's registry drift on day one. *Lead with the verified contract; treat no-over-fetch / no-N+1 as the valuable structural bonus.*

### The term at three levels

**1. Paradigm / banner → `Shapes`** (an architecture name, the way *Islands* names one).

**2. What a developer writes → `Shape` + `@shape`:**

```python
from chirp.data import Shape

@shape("SELECT id, text, done FROM todos WHERE list_id = :list_id AND community_id = :tenant")
@dataclass(frozen=True, slots=True)
class TodoRow:
    id: int
    text: str
    done: bool
# the block that renders TodoRow reads only id/text/done — shapecheck proves it
```

**3. The verification → `shapecheck`** (an `app.check()` category, peer to `oob_registry` / `dead` / `orphan`):

```
app.check()
  ERROR shapecheck: feed_row reads {summary} not in query columns {id, title, author}
  ERROR shapecheck: surface_contract names PlottingRoomView — no such Shape (did you mean PlottingRoomDetail?)
  PASS  shapecheck: 14 shapes verified — 0 over-fetch, 0 under-fetch, tenant scope present on all
```

---

## Why this is superior to the ORM paradigm (for the data→hypermedia-UI problem)

- **It optimizes the right unit.** An ORM hands you a general-purpose object graph; a hypermedia app renders *blocks*, each needing a *specific shape*. Shapes fetch exactly that — no reshaping, no impedance mismatch.
- **It verifies end-to-end.** Only a framework that owns the query *and* the template *and* the fragment can verify the path from SQL column → frozen shape → rendered block. No ORM can (it can't know what a template lazily touches); no SQL tool reaches the template; no GraphQL tool reaches server-rendered HTML. **This is the one-framework moat.**
- **It stays frozen / explicit / stateless / free-threading-clean.** Frozen shapes flow safely into concurrent/streamed renders; no hidden I/O fires mid-stream from a template.

### Honest boundary (where it does NOT win)

- **Exploratory / ad-hoc querying** — an ORM REPL is more ergonomic for one-offs.
- **Deeply object-centric, mutable domain logic** — fits an ORM's identity map better.
- Shapes is superior **for the data→hypermedia-UI problem**, the only problem Chirp targets. It is not universally superior, and the RFC must not claim so.

---

## Non-goals (explicit)

Shapes is **not** an ORM and never becomes one:

- No identity map, no unit-of-work, no session.
- No lazy loading / attribute-triggered queries.
- No mutable tracked entities (output is always frozen).
- No model-as-source-of-truth navigation (`order.customer.address`).

For genuine ORM needs: use **SQLAlchemy Core alongside** Chirp, or run **Django** for that slice. (Updates #162: the ORM entry becomes "no *stateful* ORM; yes a schema-source-of-truth + Shapes," not a blanket refusal.)

---

## Design requirements (forced by the elbysodic validation)

These are first-class requirements, not nice-to-haves. Each is grounded in the real app.

1. **Computed / derived / policy members are first-class.** elbysodic read models carry **115 `@property` fields** (badges, `rendered_body`, `can_edit`, time labels) — roughly *half* a card's read footprint. The contract must verify *"block reads ⊆ (fetched columns **+ declared computed members**)"*, or the "verified end-to-end" claim is only half true. **Most important refinement.**
2. **Tenant-scoping is a compiler primitive.** `community_id` threads through every elbysodic query. The compiler must structurally inject the scope key into every generated SELECT/join, and `shapecheck` must **FAIL** if any compiled query lacks it. Non-negotiable for the multi-tenant class.
3. **Page-composite Shapes, not only per-block.** The dominant real unit is the per-page composite (`BoardPage` = one 14-field shape; only 2 files touch `Fragment`/`OOB`). Support a declared composite that fans out to **one batched query set** shared across a page's blocks, with per-block read-subset checks layered on top — never "one query per block" (it explodes query count and fights the batching invariant).
4. **Respect the repository/service seam.** `db/AGENTS.md` forbids template-facing SQL. Co-locate the *shape declaration* with the block, but materialize the generated SQL **behind** the repository boundary.
5. **Ship a codegen / migration path.** A mature app is a near-complete shape catalog (elbysodic: 276 named-column SELECTs, 145 frozen models). A tool that ingests existing SELECTs + frozen row models and emits Shapes + the startup check turns the biggest adoption risk (re-architecture) into a one-time migration — and **audits the existing surface registry on day one** (surfacing drift like `PlottingRoomView`).
6. **The check is bidirectional.** Flag **under-fetch** as well as over-fetch, so teams can delete defensive `| default(none)` template guards.

---

## The compiler (the hard core)

The shape→SQL compiler is the make-or-break. elbysodic demonstrates *both* success and failure in one codebase: the board path batches correctly (≤150 queries at 30 threads); the claims path leaks unbounded. Requirements:

- Compile a (possibly nested) declared shape into **one batched query set** (single SELECT + `IN`-list joins / batched follow-ups), never per-row fetches.
- Inject tenant scope (req. 2) into every statement.
- Support permission-filtered / conditionally-assembled children (e.g. location-only sibling boards) without falling back to per-row queries.
- If a shape cannot be expressed in the supported SQL, **fail loud at startup** (consistent with #143's "fail-loud on unexpressible diffs").

If the compiler is weak, the no-N+1 property leaks — so this condition gates the superiority claim and ships behind the verification work, not before it.

## Verification (`shapecheck`)

- Static analysis of each block's field reads (extending the existing `block_metadata().depends_on` machinery) ⊆ (query columns + declared computed members).
- FAIL on: over-fetch, under-fetch, missing tenant scope, surface-registry names with no backing Shape.
- Honest soundness limit: templates read dynamically (loops, macros, computed). The check is **best-effort static** with explicit escape hatches; it catches the overwhelming common case loudly — it is not a soundness proof. (Mirror the caveat the reactive `depends_on` work already hit, where `url_for`/`error` appeared as false fields.)

---

## Conditions-for-superiority scorecard (from elbysodic)

| Condition | Status on the real app |
|---|---|
| #1 Nested-shape→SQL compiler | **Partially met / proven fragile** — board batches; claims leaks unbounded |
| #2 Trustworthy read-subset check | **Unmet — the highest-value gap** (registry drift is live and undetected) |
| #3 Writes stay explicit | **Met for free** — 104 raw INSERT/UPDATE, zero ORM markers |
| #4 Codegen offsets ceremony | **Favorable but binding** — must also capture the 115 computed members |

**~50–60%** of the read-side `db/repositories` + reshaping layer is absorbed (row mappers, SELECT lists, batch-loaders, memoization). Writes are untouched; the policy/presentation slice survives unless computed members are modeled (req. 1).

---

## Rollout / phasing

1. **Foundation** — depends on **#143** (working schema introspection) and builds on **#159** (typed-SQL data layer as a contract). No Shapes work lands before introspection is real.
2. **Verification first** — ship `shapecheck` (req. 1, 2, 6) against *hand-written* Shapes before the compiler. This delivers the marquee value (catches drift) at lowest risk and earns trust.
3. **Compiler** — the nested/batched/tenant-scoped query generator (gated behind verification soak).
4. **Page-composite + repository-seam** modes (req. 3, 4).
5. **Migration tool** (req. 5) — turns mature apps from "re-architect" into "migrate," and audits their registries.

## Open questions / Stop-and-Ask

- **Stewards**: data, templating, and contracts owners must sign off — this spans all three surfaces.
- **Co-location vs. governance**: does shape-declaration-at-the-block violate the "no template-facing SQL" boundary, or is materializing-behind-the-repository sufficient? (req. 4)
- **Computed-member modeling**: declaration syntax for non-column members so the contract is whole (req. 1).
- **Static-check soundness**: how aggressive before false positives on dynamic templates push teams to disable it?
- **CRUD/admin generation**: does the schema-source-of-truth + Shapes unlock a `chirp gen crud` scaffolder (the philosophy-compliant answer to Django admin)? Track separately; do not scope-creep this RFC.

---

## Summary

Shapes turns Chirp's *"SQL in, frozen dataclasses out"* stance into a **verified contract from SQL column to rendered DOM block**, checked at startup — the one thing no ORM, SQL tool, or GraphQL layer can offer, because only Chirp owns both ends. Validated against a real database-heavy app: it absorbs the majority of hand-rolled read plumbing and catches a class of bug that app cannot currently see — provided we model computed members, make tenant-scoping a primitive, support page-composites, respect the repository seam, ship a migration path, and check both directions. It is Chirp's answer to the ORM paradigm: not by copying it, but by being superior *for the one problem Chirp exists to solve.*
