---
title: Shapes
description: Verified SQL-to-render data contracts — SQL in, frozen shape out, checked before you serve a byte
draft: false
weight: 30
lang: en
type: doc
tags: [shapes, data, contracts, sql]
keywords: [shape, shapecheck, registry drift, under-fetch, over-fetch, tenant scope, nested, composite, repository seam, shapes-codegen]
category: guide
---

## Overview

**Shapes** are verified SQL-to-render data contracts. A *Shape* is a frozen,
slotted dataclass that declares — co-located with the row model — the `SELECT`
that produces it. The declared SQL is the single source of truth for what columns
the row carries, and `app.check()` verifies, at startup, that every template
block reads only fields the Shape actually fetched.

The shape is the intent: SQL in, a frozen shape out, checked before you serve a
byte. You write a `:name`-parameterized `SELECT` once, decorate the row model
with `@shape`, and the framework gives you typed fetches, automatic driver
dialect handling, and a static contract that catches drift between your SQL and
your templates.

The marquee value is honest and specific: Shapes give you a **field-level and
registry-drift startup contract**. The `shapecheck` category fails the build when
a surface contract names a Shape that no longer exists, or when a block reads a
column the bound Shape never fetched. It does **not** make N+1 queries
impossible in general — but the nested compiler does give a *bounded* query count
for the relationships you declare with `nested()`.

:::{note}
Shapes build on the [[docs/build-apps/forms-data/database|Database]] layer. The
same "SQL in, frozen dataclasses out" model applies — Shapes add a declared SQL
sidecar, the `shapecheck` contract, and the bounded nested/composite compilers on
top. Import everything from `chirp.data`.
:::

## Declaring a Shape with `@shape`

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
`ShapeError` if it is not — a mutable or unslotted target is a declaration bug,
not something to paper over at runtime.

### Fetching rows

`Shape` exposes three async classmethods. Each takes the Shape class
positionally, the `Database` positionally, then `:name` placeholder values as
keyword arguments:

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

The accessor classmethods expose the declared metadata without running anything:
`Shape.sql(cls)`, `Shape.columns(cls)` (the parsed `SELECT` output columns, or
`()` when opaque), and `Shape.computed(cls)`.

### `:name` parameter binding

You always write `:name` placeholders. The driver dialect is resolved in one
place at fetch time — SQLite gets `?`, PostgreSQL gets `$N` — and parameter
values are **never** concatenated into the SQL text, so binding stays
injection-safe:

```python
@shape("SELECT id, title FROM boards WHERE community_id = :community AND id = :id")
@dataclass(frozen=True, slots=True)
class BoardDetail:
    id: int
    title: str

board = await Shape.fetch_one(BoardDetail, db, community=1, id=42)
```

A placeholder referenced but not passed raises `ShapeError`. A repeated `:name`
reuses the same value (SQLite repeats it positionally; PostgreSQL reuses one
`$N`). PostgreSQL `::cast` syntax is passed through verbatim — it is not a
placeholder.

:::{note}
Opaque SQL — `SELECT *`, expression projections, CTEs (`WITH`), `UNION` — parses
to `columns = ()`. This is an explicit escape hatch: `shapecheck` treats an
opaque Shape as "skip, never false-positive" rather than guessing its columns.
The cost is that opaque Shapes cannot be field-verified or tenant-scoped (see
below), so prefer an explicit column list when you want the contract.
:::

## Computed members

A Shape often exposes derived values that are not `SELECT` columns. There are two
idioms, and `shapecheck` understands both.

The first is a `@property` or method on the dataclass — the reason to use a
dataclass over a tuple. These resolve at runtime and are recognized as **derived
accessors** automatically (no declaration needed):

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

A template reading `{{ member.full_name }}` is never flagged — `full_name` is a
real attribute, not a column typo.

The second idiom is the `computed=` argument, for derived members that a block
reads as `shapevar.field` but that the dataclass does not expose as an attribute
(for example, a value injected into the render context elsewhere, or a member you
want to widen the verified field set with). Declaring it tells `shapecheck` the
read is intentional:

```python
@shape("SELECT id, title FROM boards WHERE id = :id", computed=("badge",))
@dataclass(frozen=True, slots=True)
class BoardCard:
    id: int
    title: str
```

Now `{{ board.badge }}` is treated as Shape-provided. Reading an *undeclared*
member that is neither a column, an accessor, nor a `computed=` entry is an
under-fetch ERROR (next section).

## The `shapecheck` contract

`shapecheck` is an `app.check()` category that verifies the **render** side of a
`@shape` model: the fields a template block reads must be fields the bound Shape
actually fetched (`SELECT` columns) or declared (`computed=`), and surface-contract
names must resolve to a real registered Shape.

It owns four statically-decidable claims:

| Claim | Default severity | Meaning |
|-------|------------------|---------|
| Registry drift | ERROR | A surface contract names a Shape that no registered Shape backs (typo or renamed-away view). |
| Under-fetch | ERROR | A block reads `shapevar.field` where `field` is neither a `SELECT` column nor a declared `computed` member — it would silently render as `None`. |
| Over-fetch | WARNING | A Shape column no bound block reads. |
| Un-injectable scope | ERROR | A Shape declares `scope=` but its SQL is opaque, so the tenant-scope predicate cannot be injected (see [Tenant scoping](#tenant-scoping)). |

Why these severities: registry drift and under-fetch are zero-false-positive and
fail loud — a build that would render `None` or name a missing view should not
ship. Over-fetch is a WARNING because static block coverage is incomplete (loop
and macro reads are invisible), so a "column never read" claim is humble by
default. The contract emits one INFO **PASS** line summarizing the count of
verified `(template, block, Shape)` bindings when bindings verified clean and no
ERROR fired.

`shapecheck` cannot double-fire with the `data` contract: `data` matches only
`db.fetch(cls, sql)` db-handle receivers, while `Shape.fetch(...)` has the
`Shape` class as its receiver. The two categories fire on disjoint call sites.

### Severity levers

Every claim is promotable or demotable per app:

```python
from chirp.contracts.types import Severity

app.override_contract_severity("shapecheck", Severity.ERROR)   # promote over-fetch
app.override_contract_severity("shapecheck", Severity.WARNING) # soften during migration
app.override_contract_severity("shapecheck", Severity.INFO)
```

Promoting over-fetch to ERROR is useful once your templates are loop/macro-light
and you want every fetched column accounted for.

### Worked under-fetch example

Suppose a template defensively guards a value that might be missing:

```html
{% block detail %}
  <h1>{{ board.title }}</h1>
  <p>{{ board.author | default(none) }}</p>
{% endblock %}
```

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

```
ERROR  shapecheck  Block 'detail' reads 'board.author', but Shape
       'BoardCard' neither fetched nor declared 'author'.
       Add 'author' to the SELECT, or declare it computed via
       @shape(..., computed=('author',)); then delete the
       '| default(none)' guard. Shape provides: id, title.
```

Add `author` to the `SELECT` (or `computed=`), and the check goes green. Now the
value is guaranteed present, so you can **delete the `| default(none)` guard** —
the contract has replaced a defensive runtime fallback with a startup guarantee.

### When shapecheck stays silent (escape hatches)

`shapecheck` is a fail-loud ERROR category, so a false positive would break the
build in debug. It is built skip-not-guess: the field-level claim is made *only*
for single-object `shapevar.field` access, and the following are subtracted from a
block's reads before any field claim. If your read falls into one of these, the
check is intentionally silent:

- **Template globals** — `url_for`, `csrf_token`, `csp_nonce`, `range`, `len`,
  and any other name registered as an environment global. They leak into the
  block's dependency set but are not Shape fields.
- **Block-local bindings** — names bound *inside* the block via `{% set %}`,
  `let`, `export`, `capture`, `def`, or `region`, plus `{% for %}` loop targets
  (including tuple targets) and macro/`def` parameters.
- **The literal context keys `error` and `form`** — reactive dependency-analysis
  noise, never Shape fields. (Suspense's injected `__chirp_defer_pending__` key
  is subtracted too.)
- **Derived accessors** — a `shapevar.name` read where `name` is a real
  class-level attribute (a `@property`, method, or descriptor) on the bound
  dataclass but not a dataclass field. These resolve at runtime and render
  correctly; the columns they consume live inside the accessor body where the
  dependency analysis cannot see them. Reading one also suppresses the
  over-fetch claim for that binding (its column coverage is invisibly incomplete).
- **Loop-collapsed reads** — in `{% for c in cards %}...{{ c.field }}{% endfor %}`,
  only the collection root `cards` appears in the block's dependency set; the
  per-item `c.field` reads are invisible. `shapecheck` verifies the root is
  bound, not the per-item fields.
- **Macro / `def`-arg reads** — the def name leaks into dependencies, but field
  reads behind an arg name do not.
- **Opaque Shapes** — `SELECT *` / expression projections / CTE / UNION resolve
  to `columns == ()`, an explicit escape hatch with no field claims.
- **Framework templates** — anything under `chirp/` or `chirpui/` is skipped.

Only the *first* attribute of a dotted path is ever checked: `board.meta.created`
checks `meta`, never `created`; `board.title.upper()` checks `title` (a real
column), never `.upper`. Genuine typos still fire even on a Shape that also has a
derived accessor — the escape hatches narrow the claim, they do not swallow real
drift.

## Registry drift detection

Registry drift is the headline check. Every `@shape` is auto-registered by name
(its class name, or an explicit `name=`), so the framework keeps a process-wide
registry of named Shapes. A **surface contract** is a mapping from a surface name
(a page, a view, an endpoint) to the Shape name that backs it. You register it as
contract-check data:

```python
app.set_contract_check_data("surface_contracts", {
    "board-page": "BoardView",
    "board-detail": "BoardDetail",
})
```

At `app.check()` time, `shapecheck` resolves every surface-contract target
against the live registry. A target that resolves to no registered Shape — a typo
or a view that was renamed away — is an ERROR, with a closest-match suggestion:

```
ERROR  shapecheck  Surface contract 'board-page' names Shape
       'BoardViwe', but no such Shape is registered.
       Register a @shape-decorated row model named 'BoardViwe', or
       fix the surface-contract name. Did you mean 'BoardView'?
```

This check is fully static (registry-name → backing-class resolution), zero
false-positive, and runs even with no other contract data registered — the auto
registry is always consulted. It is the highest-value claim because it catches
the failure that is otherwise invisible until a user hits the page.

Same-name collisions are fail-loud, not last-wins-silently: registering the same
class under a name is idempotent, but registering a *different* class under an
already-used name raises `ShapeError`. Give one of them a distinct
`@shape(..., name=...)`.

## Nested and batched Shapes

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

`Shape.fetch(BoardDetail, db, id=1)` returns boards with their cards, and each
card with its comments — all frozen.

### Bounded query count

The compiler runs **one** batched `IN`-list query per child *level*, never one
query per parent row. For a tree of depth *d* the total is exactly `1 +
num_child_levels` queries, **independent of the row count**. The depth-2 tree
above is always three queries — one for boards, one for all their cards, one for
all those cards' comments — whether there is one board or three hundred. The
compiler collects the distinct parent keys, runs the single batched query, groups
children by their join column, and rebuilds each parent via
`dataclasses.replace`.

```python
arguments = (BoardDetail, db)
boards = await Shape.fetch(*arguments, id=1)   # 3 queries regardless of N
```

### Nested fields come last

The empty-tuple default that `nested()` sets imposes an ordering rule: **every
`nested()` field must come after all scalar fields**. `@shape` fails loud with a
clear `ShapeError` if a scalar field is declared after a nested field, rather
than letting Python raise the opaque "non-default argument follows default
argument."

### Fail-loud on unexpressible relationships

A nested relationship the bounded compiler cannot express is caught at startup,
not silently degraded. `Shape.validate(cls)` (run by `shapecheck`) raises
`ShapeError` when:

- the child SQL is opaque (`SELECT *` / CTE / UNION / no analyzable `FROM`), so
  the batched `WHERE {on} IN (...)` query cannot be built;
- the child does not carry its `on` join column as a dataclass field (the
  compiler needs it to group children);
- the parent does not carry the `key` field the `IN` list seeds from.

`optional=True` skips the child level for parents whose `key` value is `None`.
Streaming is incompatible with nested assembly (the compiler must buffer parents
to batch children), so `Shape.stream` on a Shape with `nested()` children raises
`ShapeError` — use `Shape.fetch` instead.

## Tenant scoping

Declare a tenant scope with `scope="community_id"`. The guarantee is delivered by
**structurally injecting** the scope predicate into every compiled statement —
the parent query *and* every batched child `IN`-list query — not by scanning for a
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

The compiler rewrites `SELECT id, title FROM boards` into `SELECT id, title FROM
boards WHERE community_id = :scope`, and the child `IN`-list query is scoped the
same way — so a cross-tenant child row that happens to join to an in-tenant
parent is excluded. Injection is idempotent: if you already wrote the predicate,
it is not duplicated.

### Fail-loud when un-injectable

The scope guarantee is unconditional. If a scoped Shape's SQL is opaque — a CTE,
a `UNION`, a `SELECT *`, or anything with no analyzable `FROM` — the compiler
**cannot** inject the predicate, so it refuses rather than ship a query that would
silently query across tenants. This surfaces two ways:

- `shapecheck` reports an ERROR at startup for any scoped Shape your app uses
  whose SQL is un-injectable, with a closest-match-free message naming the scope
  key.
- `Shape.fetch` / `Shape.validate` raise `ShapeError` directly.

```
ERROR  shapecheck  Shape 'SecretBoard' declares scope='community_id', but its
       SQL is opaque/un-injectable (CTE / UNION / SELECT * / no analyzable
       FROM): the tenant-scope predicate cannot be structurally injected.
```

The fix is always to rewrite the SQL as a simple single `SELECT` with an explicit
column list and an analyzable `FROM`.

## Page-composite Shapes

A `@composite` aggregates several Shapes for one page so the page declares its
data **once**. Each field is a single Shape (loaded with `fetch_one`) or a
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
threaded to every member Shape that declares a matching `scope=`, so members
inherit the page's single declaration. A field that is not a Shape member fails
loud at decoration with `ShapeError` — a composite is declared entirely in terms
of Shapes.

### The repository seam

Shapes co-locate the SQL declaration with the block's row model, and the compiled
SQL materializes **behind** `chirp.data` — the `Database` facade reached through
`Shape.fetch` and `Composite.load`. There is deliberately **no** render-time API
that accepts a raw SQL string: no return type (`Template`, `Fragment`, `Page`,
`OOB`, `Suspense`, `Stream`, `EventStream`) takes a `sql` parameter. SQL lives
only on the `@shape` / `@composite` declarations; the frozen result — never a SQL
string — is what reaches the template.

The principle is one-directional: declare a Shape next to the block that renders
it, hand the loaded frozen result to the template, and never thread a SQL string
through a handler kwarg into a render. The composite is where a page's data lives;
loading it is the repository boundary.

## Migrating an existing app: `chirp shapes-codegen`

`chirp shapes-codegen` helps you adopt Shapes incrementally, view by view. It has
two jobs, both non-destructive.

**Suggest `@shape` decorators (default).** Scan Python modules for frozen
dataclasses sitting near an explicit named-column `SELECT` literal, pair each
dataclass to the `SELECT` whose output columns are a subset of its fields, and
print a `@shape(...)` suggestion above each match:

```bash
chirp shapes-codegen pages/
```

```
--- pages/boards.py:14 (BoardView)
+ @shape('SELECT id, title FROM boards WHERE id = :id')
  @dataclass(frozen=True, slots=True)
  class BoardView:  # columns: id, title
3 @shape suggestion(s) (dry-run — no files written).
```

This is a preview only — nothing is written. `--dry-run` is the explicit, safe
default (and the only write behavior in v1). Already-decorated classes are
skipped (incremental), and only `SELECT`s the conservative parser can read are
paired, so a suggestion is always one `shapecheck` can later verify (`SELECT *` /
expressions / CTE / UNION are skipped).

**Audit drift (`--audit`).** Load an app and report every surface-contract name
with no backing Shape, reusing the exact registry-drift logic `app.check()` runs.
The `path` argument becomes an app import string, and the command exits non-zero
when drift is found, so it drops into CI:

```bash
chirp shapes-codegen myapp:app --audit
```

```
Shape drift: 1 surface contract(s) name no registered Shape.
  Surface contract 'board-page' names Shape 'BoardViwe', but no such Shape is registered.
    Register a @shape-decorated row model named 'BoardViwe', or fix the surface-contract name. Did you mean 'BoardView'?
```

| Flag | Purpose |
|------|---------|
| `path` | Directory/file to scan (default `.`); with `--audit`, an app import string like `myapp:app`. |
| `--dry-run` | Print suggested `@shape` decorators without writing files (default behavior). |
| `--audit` | Audit the app's `surface_contracts` registry for names with no backing Shape; exit non-zero on drift. |
| `--migrations DIR` | Migrations directory (reserved for future incremental codegen output). |

## Error handling

All Shape declaration and execution errors raise `ShapeError` (importable from
`chirp.data`). A `ShapeError` means a declaration is wrong — a non-frozen target,
a missing placeholder value, an un-injectable scoped Shape, an unexpressible
nested relationship, or a name collision — and is meant to fail loud, not be
caught and ignored.

## Next Steps

- [[docs/build-apps/forms-data/database|Database]] — the SQL-in, frozen-out layer Shapes build on
- [[docs/quality/contracts-debugging/categories|Contract Category Reference]] — `app.check()` categories and severity overrides
