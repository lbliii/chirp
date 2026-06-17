---
title: Shapes
description: Declare the SQL for a row next to the dataclass it fills, then verify at startup that your templates only read columns that SQL fetched.
draft: false
weight: 30
lang: en
type: doc
tags: [shapes, data, contracts, sql]
keywords: [shape, shapecheck, registry drift, under-fetch, over-fetch, tenant scope, nested, composite, repository seam, shapes-codegen]
category: guide
---

Shapes let you declare the SQL for a row right next to the dataclass it fills,
then verify at startup that your templates only read columns that SQL actually
fetched. You write a `:name`-parameterized `SELECT`, decorate a frozen dataclass
with `@shape`, and `app.check()` proves the contract before you serve a request.

Reach for a Shape when a template block renders a stable, named row that you'd be
unhappy to see silently render `None`. The contract catches drift between your SQL
and your template that is otherwise invisible until a user hits the page.

:::{since} 0.8
:::

Shapes sit on top of the [[docs/build-apps/forms-data/database|Database]] layer —
same "SQL in, frozen dataclasses out" model, with a declared SQL sidecar and a
startup contract added on top. Import everything from `chirp.data`. For one-off or
dynamic queries, use `db.fetch` or the `Query` builder instead (see the decision
table below).

The honest scope line: Shapes give you a **field-level startup contract** and
**bounded query counts** for the relationships you declare with `nested()`. They
do not make N+1 queries impossible in general.

## `@shape` vs `db.fetch` vs `Query`

Reach for `@shape` when a block needs a *verified, co-located* row contract. Reach
for a plain `db.fetch` when the query is one-off, dynamic, or deliberately opaque
(a `SELECT *`, an aggregate, a hand-tuned join). Reach for the `Query` builder when
you compose a `WHERE` clause programmatically from optional filters at request time.

:::{list-table}
:header-rows: 1

* - Reach for
  - When
  - What you get
  - What you give up
* - `@shape`
  - A block renders a stable, named row you want verified, nested, or tenant-scoped
  - Field-level + registry-drift startup contract, bounded `nested()` batching, `scope=` injection, co-located SQL
  - Fixed SQL shape (dynamic `WHERE` belongs in `Query`); opaque SQL can't be field-verified
* - `db.fetch`
  - A one-off, dynamic, or opaque query — aggregates, ad-hoc joins, `SELECT *`
  - Full SQL freedom, zero ceremony
  - No startup contract; drift is invisible until a user hits the page
* - `Query`
  - A `WHERE` / `ORDER BY` / `LIMIT` assembled from optional, request-time filters
  - Immutable chainable builder, transparent `.sql` / `.params`
  - No contract; you bind a plain dataclass, not a Shape
:::

Rule of thumb: if the same `(template, block, row model)` triple ships in every
render and you'd be sad to find it silently rendering `None`, it wants a Shape. If
the SQL is computed per request, it wants `Query`. Everything else is `db.fetch`.

## Declare a Shape

Decorate a `@dataclass(frozen=True, slots=True)` row model with `@shape("SELECT
...")`. The decorated class *is* the row type — `@shape` is an identity decorator
that attaches an immutable metadata sidecar and registers the Shape by name.

```python
from dataclasses import dataclass
from chirp.data import Shape, shape

@shape("SELECT id, title FROM boards WHERE id = :id")
@dataclass(frozen=True, slots=True)
class BoardView:
    id: int
    title: str
```

The dataclass **must** be frozen and slotted. `@shape` fails loud with a
`ShapeError` otherwise — a mutable or unslotted target is a declaration bug, not
something to paper over at runtime.

### Fetch rows

`Shape` exposes three async methods. Each takes the Shape class positionally,
the `Database` positionally, then `:name` placeholder values as keyword arguments:

```python
# All matching rows -> list[BoardView]
boards = await Shape.fetch(BoardView, db, id=42)

# First row or None -> BoardView | None
board = await Shape.fetch_one(BoardView, db, id=42)

# Incremental iteration -> AsyncIterator[BoardView]
async for board in Shape.stream(BoardView, db, id=42):
    ...
```

| Method | Returns | Notes |
|--------|---------|-------|
| `Shape.fetch(cls, db, **params)` | `list[T]` | All rows as frozen dataclasses |
| `Shape.fetch_one(cls, db, **params)` | `T \| None` | First row, or `None` |
| `Shape.stream(cls, db, **params)` | `AsyncIterator[T]` | Yields rows incrementally |

The accessor methods expose the declared metadata without running anything:
`Shape.sql(cls)`, `Shape.columns(cls)` (the parsed `SELECT` output columns, or `()`
when opaque), and `Shape.computed(cls)`.

### `:name` parameter binding

You always write `:name` placeholders. The driver dialect is resolved in one place
at fetch time — SQLite gets `?`, PostgreSQL gets `$N` — and parameter values are
**never** concatenated into the SQL text, so binding stays injection-safe:

```python
@shape("SELECT id, title FROM boards WHERE community_id = :community AND id = :id")
@dataclass(frozen=True, slots=True)
class BoardDetail:
    id: int
    title: str

board = await Shape.fetch_one(BoardDetail, db, community=1, id=42)
```

A placeholder referenced but not passed raises `ShapeError`. A repeated `:name`
reuses the same value. PostgreSQL `::cast` syntax passes through verbatim, and a
colon inside a string literal (a time literal like `'12:30:00'`) is not misread as
a placeholder — the binder is comment- and quoted-string aware.

:::{note}
Opaque SQL — `SELECT *`, expression projections, CTEs (`WITH`), `UNION` — parses to
`columns = ()`. This is an explicit escape hatch: the contract treats an opaque
Shape as "skip, never false-positive" rather than guessing its columns. The cost is
that opaque Shapes cannot be field-verified or tenant-scoped, so prefer an explicit
column list when you want the contract.
:::

### Computed members

A Shape often exposes derived values that are not `SELECT` columns. There are two
idioms, and the contract understands both.

A `@property` or method on the dataclass resolves at runtime and is recognized as a
**derived accessor** automatically — no declaration needed:

```python
@shape("SELECT id, first_name, last_name FROM members WHERE id = :id")
@dataclass(frozen=True, slots=True)
class Member:
    id: int
    first_name: str
    last_name: str

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"
```

A template reading `{{ member.full_name }}` is never flagged.

The `computed=` argument is for derived members a block reads as `shapevar.field`
that the dataclass does not expose as an attribute (a value injected into the render
context elsewhere). Declaring it tells the contract the read is intentional:

```python
@shape("SELECT id, title FROM boards WHERE id = :id", computed=("badge",))
@dataclass(frozen=True, slots=True)
class BoardCard:
    id: int
    title: str
```

Now `{{ board.badge }}` is treated as Shape-provided.

## Why a Shape earns its keep: the under-fetch contract

The `shapecheck` category runs inside `app.check()` and verifies the **render**
side of a `@shape` model: the fields a block reads must be fields the bound Shape
fetched (`SELECT` columns) or declared (`computed=`). A read of a field the Shape
never provided — one that would silently render as `None` — is an ERROR.

:::{example} A defensive guard becomes a startup guarantee
A template defensively guards a value that might be missing:

```html
{% block detail %}
  <h1>{{ board.title }}</h1>
  <p>{{ board.author | default(none) }}</p>
{% endblock %}
```

The Shape only fetches `id` and `title`:

```python
@shape("SELECT id, title FROM boards WHERE id = :id")
@dataclass(frozen=True, slots=True)
class BoardCard:
    id: int
    title: str

async def board_detail():
    board = await Shape.fetch_one(BoardCard, get_db(), id=1)
    return Fragment("board.html", "detail", board=board)
```

`app.check()` reports:

```text
ERROR  shapecheck  Block 'detail' reads 'board.author', but Shape
       'BoardCard' neither fetched nor declared 'author'.
       Add 'author' to the SELECT, or declare it computed via
       @shape(..., computed=('author',)); then delete the
       '| default(none)' guard. Shape provides: id, title.
```

Add `author` to the `SELECT` (or `computed=`) and the check goes green. The value is
now guaranteed present, so you can **delete the `| default(none)` guard** — the
contract has replaced a defensive runtime fallback with a startup guarantee.
:::

`shapecheck` owns four claims, with these default severities:

| Claim | Default severity | Meaning |
|-------|------------------|---------|
| Registry drift | ERROR | A surface contract names a Shape no registered Shape backs. |
| Under-fetch | ERROR | A block reads a field the bound Shape never fetched or declared. |
| Over-fetch | WARNING | A Shape column no bound block reads. |
| Un-injectable scope | ERROR | A scoped Shape's SQL is opaque, so the scope predicate can't be injected. |

Registry drift and under-fetch are zero-false-positive and fail loud. Over-fetch is
a WARNING because static block coverage is incomplete (loop and macro reads are
invisible), so a "column never read" claim is humble by default. One INFO **PASS**
line summarizes the count of verified bindings when nothing errored.

`shapecheck` cannot double-fire with the `data` contract: `data` matches only
`db.fetch(cls, sql)` database-handle receivers, while `Shape.fetch(...)` has the
Shape class as its receiver. The two categories fire on disjoint call sites.

You can adjust how severe each `shapecheck` claim is with `override_contract_severity`
— but that lever is coarser than it looks.

:::{danger} Softening `shapecheck` demotes the fail-loud claims too
`override_contract_severity` operates on the **whole category**, not a single
claim. There is no per-claim targeting. Softening the category to quiet over-fetch
during a migration *also* demotes registry drift, under-fetch, and un-injectable
scope — so a build that would render `None` or query across tenants no longer fails:

```python
# Footgun: silently demotes registry drift, under-fetch, AND
# un-injectable scope to WARNING too.
app.override_contract_severity("shapecheck", Severity.WARNING)
```

To quiet over-fetch, fix or declare the unread columns (drop them from the `SELECT`,
or accept the WARNING) instead of softening the whole category.
:::

:::{dropdown} When shapecheck stays silent (escape hatches)
The field-level claim is made *only* for single-object `shapevar.field` access. The
following are subtracted from a block's reads before any field claim, so a read that
falls into one of these is intentionally not checked:

- **Template globals** — `url_for`, `csrf_token`, `csp_nonce`, `range`, `len`, and
  any name registered as an environment global.
- **Block-local bindings** — names bound inside the block via `{% set %}`, `let`,
  `export`, `capture`, `def`, or `region`, plus `{% for %}` loop targets and macro
  parameters.
- **The literal context keys `error` and `form`**, plus Suspense's injected
  `__chirp_defer_pending__` key — reactive dependency-analysis noise, never fields.
- **Derived accessors** — a read where the name is a real `@property`/method on the
  bound dataclass. (Reading one also suppresses the over-fetch claim for that
  binding, since its column coverage is invisibly incomplete.)
- **Loop-collapsed reads** — in `{% for c in cards %}{{ c.field }}{% endfor %}`, only
  the collection root `cards` appears in the dependency set; the per-item reads are
  invisible. The contract verifies the root is bound, not the per-item fields.
- **`nested()` field reads** — a nested relationship is a real dataclass field but
  not a `SELECT` column, and the contract recognizes it as Shape-provided.
- **Macro / `def`-arg reads** — the def name leaks into dependencies, but field reads
  behind an arg name do not.
- **Opaque Shapes** — `SELECT *` / expression projections / CTE / UNION resolve to
  `columns == ()`, an explicit escape hatch with no field claims.
- **Framework templates** — anything under `chirp/` or `chirpui/` is skipped.

Only the *first* attribute of a dotted path is ever checked: `board.meta.created`
checks `meta`, never `created`. The one-line takeaway: **genuine typos still fire;
globals, loop/macro reads, derived accessors, and opaque SQL are skipped.**
:::{/dropdown}

## Registry drift detection

Every `@shape` is auto-registered by name (its class name, or an explicit `name=`),
so the framework keeps a process-wide registry of named Shapes. A **surface
contract** maps a surface name (a page, a view, an endpoint) to the Shape name that
backs it. Register it as contract-check data:

```python
app.set_contract_check_data("surface_contracts", {
    "board-page": "BoardView",
    "board-detail": "BoardDetail",
})
```

At `app.check()` time, every surface-contract target is resolved against the live
registry. A target that resolves to no registered Shape — a typo, or a view renamed
away — is an ERROR with a closest-match suggestion:

```text
ERROR  shapecheck  Surface contract 'board-page' names Shape
       'BoardViwe', but no such Shape is registered.
       Register a @shape-decorated row model named 'BoardViwe', or
       fix the surface-contract name. Did you mean 'BoardView'?
```

This check is fully static, zero false-positive, and runs even with no other
contract data registered — it catches the failure that is otherwise invisible until
a user hits the page. Registering a *different* class under an already-used name
raises `ShapeError`; give one of them a distinct `@shape(..., name=...)`.

## Nested and batched Shapes

:::{since} 0.8
:::

Declare a parent-child relationship on a Shape field with `nested(child, *, on,
key, optional=False)`. The child must itself be a `@shape`-decorated Shape (it
carries its own SQL):

```python
@shape("SELECT id, card_id, body FROM comments WHERE card_id = :card_id")
@dataclass(frozen=True, slots=True)
class Comment:
    id: int
    card_id: int
    body: str

@shape("SELECT id, board_id, title FROM cards WHERE board_id = :board_id")
@dataclass(frozen=True, slots=True)
class Card:
    id: int
    board_id: int
    title: str
    comments: tuple[Comment, ...] = nested(Comment, on="card_id", key="id")

@shape("SELECT id, title FROM boards WHERE id = :id")
@dataclass(frozen=True, slots=True)
class BoardDetail:
    id: int
    title: str
    cards: tuple[Card, ...] = nested(Card, on="board_id", key="id")
```

`Shape.fetch(BoardDetail, db, id=1)` returns boards with their cards, and each card
with its comments — all frozen. The query count is **independent of the child row
count**: a level that joins three comments or thirty thousand issues the same
handful of batched `IN`-list queries, never one query per parent row.

Two ordering rules to know up front: every `nested()` field must come **after** all
scalar fields (`@shape` fails loud otherwise, instead of letting Python raise the
opaque "non-default argument follows default argument"), and `Shape.stream` raises
`ShapeError` on a Shape with `nested()` children — the compiler must buffer parents
to batch children, so use `Shape.fetch` instead. `optional=True` skips the child
level for parents whose `key` value is `None`.

:::{dropdown} How the bounded query count works (and its exact ceiling)
The compiler runs a batched `IN`-list query per child *level*. The parent keys for a
level are chunked to the driver's variable limit (the historical
`SQLITE_MAX_VARIABLE_NUMBER` floor), so a level with more distinct parent keys than
the chunk size is split across a few batched queries and merged.

The total is `1 + Σ ceil(distinct_keys_per_level / chunk_size)`. For the depth-2 tree
above with a normal number of parents, that is exactly three queries — one for
boards, one for all their cards, one for all those cards' comments — and it stays
three whether each board has one comment or three hundred. Only when a single level
has thousands of distinct parent keys does it spill into additional chunk queries,
still O(chunks per level), never O(child rows). The compiler collects the distinct
parent keys, runs the batched query per chunk, merges and groups children by their
join column, and rebuilds each parent via `dataclasses.replace`.

The compiler reserves the `__chirp_` placeholder prefix (generated batch keys, the
`__chirp_rn` row number, the per-parent limit), so an author `:name` placeholder in a
child Shape must not begin with `__chirp_`. This is **enforced**: declaring such a
Shape fails loud with `ShapeError` at decoration, so a reserved-name collision can
never silently mis-bind at fetch time.
:::{/dropdown}

### Ordered and limited children

The batched rewrite **preserves a child SQL's trailing `ORDER BY` and per-parent
`LIMIT`** — it does not silently flatten "top 5 recent comments per card" into "all
comments, arbitrary order." A per-parent `LIMIT` is compiled into a window-function
top-N so each parent gets its own slice in the single batched query:

```python
@shape("SELECT id, card_id, body, created_at FROM comments "
       "WHERE card_id = :card_id ORDER BY created_at DESC LIMIT 5")
@dataclass(frozen=True, slots=True)
class Comment:
    id: int
    card_id: int
    body: str
    created_at: str
```

Now each card carries its **5 most recent** comments, ordered, batched — one query,
not one per parent. The child's own non-join `WHERE` filters (e.g. `AND deleted = 0`)
are preserved in the batched form too.

:::{dropdown} Cases the window rewrite can't express (these fail loud)
This is a **bounded top-N compilation, not a general query engine** —
`ROW_NUMBER() OVER (PARTITION BY {on} ORDER BY ...)` and only that shape. Window
functions are available on both backends (SQLite ≥ 3.25 and PostgreSQL). Cases the
rewrite cannot express deterministically **fail loud at startup** rather than degrade
into "all rows, arbitrary order":

- a `LIMIT` with **no `ORDER BY`** (the per-parent top-N would be nondeterministic);
- an `OFFSET` (it would apply globally, not per parent);
- a per-parent `LIMIT` on a child that *also* has its own nested grandchildren (the
  partition plus further batching is ambiguous);
- a join predicate the compiler cannot isolate.

`Shape.validate(cls)` also raises `ShapeError` when a child SQL is opaque, the child
does not carry its `on` join column as a field, or the parent does not carry the
`key` field. These checks run at `app.check()` startup — `shapecheck` calls
`Shape.validate(cls)` on every Shape your app uses — so a malformed declaration is an
ERROR before you serve a byte, with `Shape.fetch` raising the same error as a runtime
backstop.
:::{/dropdown}

## Tenant scoping

:::{since} 0.8
:::

Declare a tenant scope with `scope="community_id"`. The guarantee is delivered by
**structurally injecting** the scope predicate into every compiled statement — the
parent query *and* every batched child `IN`-list query — not by scanning for a
`WHERE` column you hoped you wrote:

```python
@shape("SELECT id, board_id, title FROM cards WHERE board_id = :board_id",
       scope="community_id")
@dataclass(frozen=True, slots=True)
class Card:
    id: int
    board_id: int
    title: str

@shape("SELECT id, title FROM boards", scope="community_id")
@dataclass(frozen=True, slots=True)
class Board:
    id: int
    title: str
    cards: tuple[Card, ...] = nested(Card, on="board_id", key="id")
```

The `:scope` value threads from the fetch call:

```python
boards = await Shape.fetch(Board, db, scope=1)
```

The compiler rewrites `SELECT id, title FROM boards` into `... WHERE community_id =
:scope`, and the child `IN`-list query is scoped the same way — so a cross-tenant
child row that happens to join to an in-tenant parent is excluded.

The scope predicate is the **compiler's** to own. If your SQL already contains
exactly `community_id = :scope`, it is not duplicated — but a *different*
author-written predicate on the scope column (`community_id = :tenant`,
`community_id IN (...)`) is a fail-loud `ShapeError`. Remove the hand-written
predicate and let the compiler inject it.

:::{dropdown} When tenant scope can't be injected (fails loud)
The scope guarantee is unconditional. If a scoped Shape's SQL is one the compiler
cannot structurally analyze a single outer `WHERE` target on, it refuses rather than
ship a query that would silently query across tenants. That covers the opaque cases
(a CTE, a `UNION`, a `SELECT *`, no analyzable `FROM`) **and** any outer query whose
`FROM` is a derived table or subquery, or that carries a correlated/scalar subquery —
there, naively appending `AND community_id = :scope` would attach to the *inner*
subquery's `WHERE` and produce invalid or unscoped SQL. This surfaces as a
`shapecheck` ERROR at startup and a `ShapeError` from `Shape.fetch` / `Shape.validate`:

```text
ERROR  shapecheck  Shape 'SecretBoard' declares scope='community_id', but its
       SQL is opaque/un-injectable (CTE / UNION / SELECT * / derived-table or
       subquery FROM / no single analyzable WHERE target): the tenant-scope
       predicate cannot be structurally injected.
```

The fix is to rewrite the SQL as a simple single `SELECT` with an explicit column
list and one analyzable `FROM`.
:::{/dropdown}

## Page-composite Shapes

:::{since} 0.8
:::

A `@composite` aggregates several Shapes for one page so the page declares its data
**once**. Each field is a single Shape (loaded with `fetch_one`) or a
`tuple[Shape, ...]` (loaded with `fetch`):

```python
from chirp.data import Composite, composite

@composite(scope="community_id")
@dataclass(frozen=True, slots=True)
class BoardPage:
    board: Board                  # single-object member -> fetch_one
    members: tuple[Member, ...]   # sequence member -> fetch
    activity: tuple[Event, ...]
```

`Composite.load` runs the batched query set across the members — one query per
member Shape (nested members reuse the bounded compiler) — coalesces the shared
`scope` and params, and returns one frozen instance:

```python
page = await Composite.load(BoardPage, db, board_id=7, scope=1)
```

The page scopes once: when the composite declares `scope=`, the `:scope` value is
threaded to every member Shape that declares a matching `scope=`, so members inherit
the page's single declaration. A field that is not a Shape member fails loud with
`ShapeError` at decoration.

:::{dropdown} The repository seam
Shapes co-locate the SQL declaration with the block's row model, and the compiled
SQL materializes **behind** `chirp.data` — the `Database` facade reached through
`Shape.fetch` and `Composite.load`. There is deliberately **no** render-time API that
accepts a raw SQL string: no return type (`Template`, `Fragment`, `Page`, `OOB`,
`Suspense`, `Stream`, `EventStream`) takes a `sql` parameter. SQL lives only on the
`@shape` / `@composite` declarations; the frozen result — never a SQL string — is
what reaches the template.

The principle is one-directional: declare a Shape next to the block that renders it,
hand the loaded frozen result to the template, and never thread a SQL string through
a handler kwarg into a render. This is the same "[[docs/about/core-concepts/return-values|the
return type is the intent]]" boundary applied to data: the composite is where a
page's data lives, and loading it is the repository boundary.
:::{/dropdown}

The Shapes data layer end-to-end — startup-verified contract, tenant `scope=`
isolation at the page *and* data layer, and a bounded `nested()` / `@composite`
dashboard whose query count stays constant as rows grow — ships as a runnable
example.

*Source: [`examples/standalone/shapes_workspaces`](https://github.com/lbliii/chirp/tree/main/examples/standalone/shapes_workspaces).*

## Migrate an existing app: `chirp shapes-codegen`

:::{since} 0.8
:::

`chirp shapes-codegen` helps you adopt Shapes incrementally, view by view. It has
two non-destructive jobs.

**Suggest `@shape` decorators (default).** Scan Python modules for frozen dataclasses
sitting near an explicit named-column `SELECT` literal, pair each dataclass to the
`SELECT` whose output columns are a subset of its fields, and print a `@shape(...)`
suggestion above each match:

```bash
chirp shapes-codegen pages/
```

```text
--- pages/boards.py:14 (BoardView)
+ @shape('SELECT id, title FROM boards WHERE id = :id')
  @dataclass(frozen=True, slots=True)
  class BoardView:  # columns: id, title
3 @shape suggestion(s) (dry-run — no files written).
```

This is a preview only — `--dry-run` is the explicit, safe default, and the only
write behavior in v1. Already-decorated classes are skipped, and only `SELECT`s the
conservative parser can read are paired, so a suggestion is always one `shapecheck`
can later verify.

**Audit drift (`--audit`).** Load an app and report every surface-contract name with
no backing Shape, reusing the exact registry-drift logic `app.check()` runs. The
`path` argument becomes an app import string, and the command exits non-zero when
drift is found, so it drops into CI:

```bash
chirp shapes-codegen myapp:app --audit
```

| Flag | Purpose |
|------|---------|
| `path` | Directory/file to scan (default `.`); with `--audit`, an app import string like `myapp:app`. |
| `--dry-run` | Print suggested `@shape` decorators without writing files (default behavior). |
| `--audit` | Audit `surface_contracts` for names with no backing Shape; exit non-zero on drift. |
| `--migrations DIR` | Migrations directory (reserved for future incremental codegen output). |

## Error handling

All Shape declaration and execution errors raise `ShapeError` (importable from
`chirp.data`). A `ShapeError` means a declaration is wrong — a non-frozen target, a
missing placeholder value, an un-injectable scoped Shape, an unexpressible nested
relationship, or a name collision — and is meant to fail loud, not be caught and
ignored.

:::{note} See also
- [[docs/build-apps/forms-data/database|Database]] — the SQL-in, frozen-out layer Shapes build on
- [[docs/build-apps/forms-data/forms-validation|Forms and validation]] — validating the data on the way in
- [[docs/quality/contracts-debugging/categories|Contract categories]] — `shapecheck` severity and overrides
- [[docs/build-apps/forms-data/_index|Forms & data]] — the section overview
:::

:::{related}
:::
