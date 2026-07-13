# Shapes dogfood: multi-tenant repository pilot

**Status:** Complete

**Issue:** [#696](https://github.com/lbliii/chirp/issues/696)

**Parent epic:** [#586](https://github.com/lbliii/chirp/issues/586)

**Downstream baseline:**
[`lbliii/elbysodic@53499fa9`](https://github.com/lbliii/elbysodic/commit/53499fa9eb6146a6019bdbd725c4f364a93baf8e)

**Audited:** 2026-07-10

## Outcome

Shapes survived contact with a real multi-tenant application as a narrow read
projection, not as a replacement repository layer.

| Slice | Decision | Boundary |
| --- | --- | --- |
| Sidebar-section CRUD | Retain application repository | Shape readback matched the repository result, but Shapes deliberately owns no write, transaction, validation, normalization, or commit behavior. |
| Tenant-scoped board list | Adopt narrowly | A stable frozen projection with `scope="community_id"` returned only the requested community. Use this for new async, template-bound projections; do not replace the existing synchronous rich-domain repository method merely to adopt Shapes. |
| Board summary read model | Retain application service/repository | A simple scoped `COUNT(*)` Shape matched repository output, but the real read model combines policy-filtered children, facets, posts, membership read state, latest objects, and Python-derived flags. `computed=` declares fields for template checking; it is not a service-computation engine. |

No Chirp extension is justified by the pilot. The accepted partial adoption is
already the documented Shapes boundary: stable fixed read projections fit;
writes, dynamic queries, opaque aggregates, policy, and orchestration stay in
the application.

## Baseline and method selection

The pilot used an untouched disposable clone at the baseline above. The
developer checkout was not modified.

The three slices were selected from these public source boundaries:

- simple CRUD: `update_sidebar_section()` validates input, updates under
  explicit community scope, commits, then calls the repository readback;
- tenant-scoped read: `list_boards(community_id)` selects a rich `Board` row
  under an explicit community predicate and maps storage values through the
  application's row mapper;
- simple aggregate: `count_threads(community_id, board_id)` returns one scoped
  count; and
- computed model: `board_summaries()` assembles `BoardSummary` from child
  visibility, facets, threads, posts, per-membership read state, latest-object
  selection, and current-face relevance.

The existing code is visible at
[`boards.py`](https://github.com/lbliii/elbysodic/blob/53499fa9eb6146a6019bdbd725c4f364a93baf8e/src/elbysodic/db/repositories/boards.py),
[`threads.py`](https://github.com/lbliii/elbysodic/blob/53499fa9eb6146a6019bdbd725c4f364a93baf8e/src/elbysodic/db/repositories/threads.py),
and
[`services/boards.py`](https://github.com/lbliii/elbysodic/blob/53499fa9eb6146a6019bdbd725c4f364a93baf8e/src/elbysodic/services/boards.py).

## Executed proof

### Existing application behavior

Four existing downstream tests passed before the experiment:

```text
tests/test_tenant_repository.py::test_boards_are_scoped_by_community
tests/test_tenant_repository.py::test_thread_counts_are_scoped_to_board_and_community
tests/test_tenant_repository.py::test_sidebar_section_config_is_scoped_by_community
tests/test_forum_slice.py::test_parent_board_summaries_roll_up_child_activity_but_thread_lists_stay_direct
```

Receipt: `4 passed` on the recorded baseline.

These tests establish the behavior the pilot was not allowed to weaken:
cross-community board isolation, board/community count isolation,
community-scoped CRUD readback, and the richer service rule that a parent
summary rolls up child activity while its direct thread list does not.

### Disposable Shapes experiment

The disposable test declared three frozen/slotted Shapes against the actual
schema:

1. a scoped sidebar-section projection read after the repository update;
2. a scoped board-list projection queried independently for two communities;
3. a scoped `COUNT(*) AS thread_count` projection for one board.

All ran through Chirp's public `Database` and `Shape.fetch()` /
`Shape.fetch_one()` paths against the same SQLite file used by the synchronous
application repository.

Receipt:

```text
3 passed
All checks passed!  # ty check of the disposable pilot
```

The experiment was intentionally not committed to the downstream repository.
It tested the framework boundary without forcing a runtime dependency, async
service conversion, or product-code change merely to produce adoption.

## Correctness and tenant isolation

`scope="community_id"` correctly injected the tenant predicate into the two
single-table Shapes. The board fixture reused the same slug in two communities;
each fetch returned only its own row. Parameter values remained separate from
SQL, and the Shape SQL used named `:parameter` placeholders.

This is stronger than copying a raw `WHERE community_id = ?` query into a page
handler because the Shape declaration carries a startup-verifiable scope
contract. It does not replace service policy. A caller must still derive the
authorized community before passing `scope=`.

## Typing and row mapping

The pilot projection types were frozen and slotted and passed `ty`. That fit is
good for small template-facing rows.

The existing repository's rich `Board` type is a different boundary. Its row
mapper converts stored strings and integers into domain enums and booleans.
Directly mapping the same SQL into that domain class would bypass application
normalization even if Python accepted the constructor values at runtime. A
Shape should therefore use a projection type whose field types match database
values, or the application should retain its repository mapper. Shape
adoption is not permission to weaken domain typing.

## CRUD and transaction ownership

The sidebar readback proved that a Shape can verify the read side of a CRUD
flow. It cannot own the flow:

- Shapes exposes `SELECT` execution only;
- the repository validates and normalizes the section key and label;
- the repository owns `UPDATE`, commit, nested transaction behavior, and
  rollback; and
- the repository returns the application domain type.

Adding Shape mutations would turn a verified read-contract feature into a
second repository/ORM surface. That is rejected. The application repository
remains authoritative for create, update, and delete behavior.

## Computed read-model ownership

The scoped count shows that a small aggregate can be represented as a Shape
when its SQL and output are stable. It does not make the real `BoardSummary` a
Shape candidate.

`BoardSummary` is assembled after multiple tenant-scoped batch reads and
policy decisions. It includes nested domain objects, membership-specific unread
state, latest-object selection, facet relevance, and visibility-filtered child
activity. Moving that work into one Shape would either:

- duplicate service policy in SQL;
- create an opaque query that loses field-level verification;
- couple template projection to SQLite-specific aggregation; or
- misrepresent `computed=` as executable computation.

The application service remains the correct owner. No new composite, aggregate,
policy-hook, or computed-value API is proposed for Chirp.

## Ergonomics and lifecycle

For the narrow read projection, the Shape declaration was compact and
`scope=` removed repeated tenant predicates. The material integration cost is
lifecycle, not declaration syntax:

- the application repository and services are synchronous `sqlite3` code;
- Shape execution uses Chirp's async `Database` facade; and
- replacing one existing repository method would push async changes through
  service protocols and callers for little product benefit.

New async rendered projections may adopt Shapes without that replacement. A
future application-wide async data migration should be planned as an
application architecture change, not smuggled into a Shapes dogfood patch.

## Migration and SQLite-to-PostgreSQL/Pelt transfer

Shapes does not own schema or migrations. The downstream application's schema,
migrations, constraints, seed data, and transaction rules remain application
authority.

The pilot's fixed single-table `SELECT`s and named parameters are structurally
portable through Chirp's SQLite/PostgreSQL placeholder binding. That is the
limit of the transfer finding. The application repository also uses
SQLite-specific behavior including PRAGMAs, `BEGIN IMMEDIATE`, `json_each`, and
integer-backed booleans. No PostgreSQL/Pelt claim follows from the SQLite
pilot.

If the application chooses PostgreSQL later, it must own schema/migration
translation, concurrency semantics, domain coercion, and live service proof.
Pelt would own driver correctness; Shapes would continue to own only the
declared read contract. No framework issue is needed before that trigger.

## Follow-up disposition

- **Chirp:** no new issue. The pilot found no missing framework contract; the
  existing docs already place CRUD, dynamic queries, opaque aggregates, and
  policy-rich read models outside Shapes.
- **Downstream application:** no immediate code issue. Narrow adoption is
  available for a new async template projection. Revisit an application-wide
  data-layer change only when PostgreSQL adoption or another product need pays
  for the sync-to-async migration.
- **Pelt:** no issue. This SQLite pilot supplies a consumer profile, not live
  PostgreSQL evidence.

No public API, runtime behavior, dependency, migration, example, scaffold,
site content, or changelog changes result from this research receipt.
