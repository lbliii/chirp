---
title: Database
description: Async SQL access that maps rows to frozen dataclasses — SQLite built in, PostgreSQL via one extra.
draft: false
weight: 10
lang: en
type: doc
tags: [database, sqlite, postgresql, async]
keywords: [database, sqlite, postgresql, asyncpg, query, row-mapping, transactions, migrations]
category: guide
---

## Overview

Chirp's data layer is a thin async query interface, not an ORM: you write SQL, and Chirp maps each row to a frozen dataclass. Reach for it when you want typed reads and writes against **SQLite** (built in, zero extra dependencies) or **PostgreSQL** (`pip install bengal-chirp[data-pg]`) without an object-relational mapper in the way.

Pass a connection URL to `App(db=...)` and every handler can run queries via `app.db` or `get_db()`. SQLite is the right default for development and single-writer apps; switch the connection string to `postgresql://...` when you need write concurrency.

## When to reach for it

:::{list-table}
:header-rows: 1

* - You want…
  - Reach for
* - Typed reads/writes from raw SQL, no ORM
  - `db.fetch` / `db.execute` (this page)
* - The same query mapped to a model-bound class with named placeholders
  - [[docs/build-apps/forms-data/shapes|Shapes]]
* - Real-time HTML pushed when a Postgres row changes
  - `db.listen()` + [[docs/build-apps/streaming-updates/server-sent-events|Server-Sent Events]]
:::

## Setup

The shortest path: pass a connection URL to `App()`. SQLite needs no extra dependency.

```python
from chirp import App, Template

app = App(db="sqlite:///app.db")
```

The database connects on startup and disconnects on shutdown. Access it via `app.db` inside any handler:

```python
@app.route("/users")
async def list_users():
    users = await app.db.fetch(User, "SELECT * FROM users")
    return Template("users.html", users=users)
```

Pass a `Database` instance instead of a URL when you need to set the pool size:

```python
from chirp.data import Database

db = Database("postgresql://user:pass@localhost/mydb", pool_size=10)
app = App(db=db)
```

### Standalone usage

Use `Database` directly without an `App` — for scripts, jobs, or tests:

```python
from chirp.data import Database

async with Database("sqlite:///app.db") as db:
    users = await db.fetch(User, "SELECT * FROM users")
```

Or manage the lifecycle yourself with `connect()` / `disconnect()`.

### `get_db()` accessor

When using `App(db=...)`, reach the database from any handler without threading it through arguments:

```python
from chirp.data import get_db

@app.route("/users")
async def list_users():
    db = get_db()
    users = await db.fetch(User, "SELECT * FROM users")
    return Template("users.html", users=users)
```

## Data models

Define frozen dataclasses whose fields match your query columns:

```python
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class User:
    id: int
    name: str
    email: str
```

Query results map to these dataclasses automatically. Extra columns are ignored, so `SELECT *` works even when the dataclass has fewer fields.

## Query methods

Five methods cover almost everything. Each takes the SQL placeholder for your driver — `?` for SQLite, `$1` for PostgreSQL (see [Parameter style](#parameter-style) below).

### `fetch` — all rows

```python
users = await db.fetch(User, "SELECT * FROM users WHERE active = ?", True)
# Returns: list[User]
```

### `fetch_one` — single row

```python
user = await db.fetch_one(User, "SELECT * FROM users WHERE id = ?", 42)
# Returns: User | None
```

### `fetch_val` — scalar value

```python
count = await db.fetch_val("SELECT COUNT(*) FROM users")
# Returns: Any — pass as_type to coerce
count = await db.fetch_val("SELECT COUNT(*) FROM users", as_type=int)
# Returns: int | None
```

### `execute` — INSERT / UPDATE / DELETE

```python
rows_affected = await db.execute(
    "INSERT INTO users (name, email) VALUES (?, ?)",
    "Alice", "alice@example.com",
)
# Returns: int (rows affected)
```

### `stream` — cursor-based iteration

For large result sets, stream rows without loading everything into memory:

```python
async for user in db.stream(User, "SELECT * FROM users", batch_size=100):
    process(user)
```

:::{note}
**Method reference**

| Method | Returns | Description |
|--------|---------|-------------|
| `fetch(cls, sql, *params)` | `list[T]` | All matching rows as dataclasses |
| `fetch_one(cls, sql, *params)` | `T \| None` | First row or `None` |
| `fetch_val(sql, *params)` | `Any` | First column of first row |
| `execute(sql, *params)` | `int` | Rows affected |
| `execute_many(sql, params_seq)` | `int` | Batch INSERT/UPDATE; total rows affected |
| `execute_script(sql)` | `None` | Run a multi-statement SQL script |
| `stream(cls, sql, *params)` | `AsyncIterator[T]` | Cursor-based row iteration |
:::

## Transactions

Wrap multiple statements in an atomic transaction. It auto-commits on a clean exit and auto-rolls back on any exception:

```python
async with db.transaction():
    await db.execute(
        "INSERT INTO orders (user_id, total) VALUES (?, ?)",
        user_id, total,
    )
    await db.execute(
        "UPDATE inventory SET stock = stock - ? WHERE product_id = ?",
        quantity, product_id,
    )
```

Two behaviors worth knowing:

- **Reads see uncommitted writes.** A `fetch_val` inside the block counts rows you just inserted but have not committed.
- **Nesting is transparent.** An inner `transaction()` joins the outer one — there is no nested savepoint, so both commit together.

```python
async with db.transaction():
    await db.execute("INSERT INTO users ...", name, email)
    async with db.transaction():  # joins the outer transaction
        await db.execute("INSERT INTO profiles ...", user_id)
    # both committed together
```

## Common patterns

### Build dynamic queries with `Query`

Simple queries are fine as raw SQL. But when filters are conditional, string concatenation gets fragile. `Query` is an immutable builder that follows the same chaining pattern as `Response.with_*()`: each method returns a new `Query`, so the original is never mutated.

```python
from chirp.data import Query

@dataclass(frozen=True, slots=True)
class Todo:
    id: int
    text: str
    done: bool

todos = await (
    Query(Todo, "todos")
    .where("done = ?", False)
    .where_if(search, "text LIKE ?", f"%{search}%")  # only added if search is truthy
    .order_by("id DESC")
    .take(20)
    .fetch(db)
)
```

Because a `Query` is frozen, you can define a base at module level and branch from it per request without any shared-state risk:

```python
from chirp import Request, Template

ALL_TODOS = Query(Todo, "todos").order_by("id")  # safe at module scope — frozen

@app.route("/todos")
async def list_todos(request: Request) -> Template:
    search = request.query.get("q")
    todos = await (
        ALL_TODOS
        .where_if(search, "text LIKE ?", f"%{search}%")
        .fetch(app.db)
    )
    return Template("todos.html", todos=todos)
```

Inspect the exact SQL before it runs — there are no hidden queries:

```python
print(q.sql)     # SELECT * FROM todos WHERE done = ? ORDER BY id DESC LIMIT 20
print(q.params)  # (False,)
```

:::{dropdown} Full Query builder reference
:icon: list

`Query` delegates execution to the same `Database` methods you already know.

| Method | Returns | Description |
|--------|---------|-------------|
| `select(columns)` | `Query[T]` | Columns to SELECT (default `*`) |
| `where(clause, *params)` | `Query[T]` | Add a WHERE clause (multiple are ANDed) |
| `where_if(cond, clause, *params)` | `Query[T]` | Add a WHERE clause only if `cond` is truthy |
| `order_by(clause)` | `Query[T]` | Set ORDER BY |
| `take(n)` | `Query[T]` | Set LIMIT |
| `skip(n)` | `Query[T]` | Set OFFSET |
| `fetch(db)` | `list[T]` | Execute and return all rows |
| `fetch_one(db)` | `T \| None` | Execute and return the first row |
| `count(db)` | `int` | `COUNT(*)` with the same WHERE clauses (ignores LIMIT/OFFSET) |
| `exists(db)` | `bool` | Whether any row matches |
| `stream(db)` | `AsyncIterator[T]` | Yield rows incrementally |
| `.sql` | `str` | The exact SQL that will execute |
| `.params` | `tuple` | The bound parameters |
:::{/dropdown}

### Batch inserts

```python
await db.execute_many(
    "INSERT INTO users (name, email) VALUES (?, ?)",
    [("Alice", "a@b.com"), ("Bob", "b@b.com"), ("Carol", "c@b.com")],
)
```

### Log every query

Pass `echo=True` to print each statement with its timing to stderr — useful while developing:

```python
db = Database("sqlite:///app.db", echo=True)
# [chirp.data]  0.3ms  SELECT * FROM users WHERE active = ?  params=(True,)
```

## Migrations

Forward-only SQL migrations live as numbered `.sql` files. Pending ones run at startup.

::::{steps}
:::{step} Create numbered `.sql` files
Name files `NNN_description.sql`, where `NNN` is a zero-padded version number. Each file is plain SQL run as a single statement.

```sql
-- migrations/001_create_users.sql
CREATE TABLE users (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name  TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE
)
```
:::{/step}
:::{step} Point the app at the directory
Pending migrations run automatically on startup, oldest first.

```python
app = App(db="sqlite:///app.db", migrations="migrations/")
```

Or run them yourself from a script with `migrate()`:

```python
from chirp.data import Database, migrate

db = Database("sqlite:///app.db")
await db.connect()
result = await migrate(db, "migrations/")
print(result.summary)
# "Applied 2 migration(s): 001_create_users, 002_add_email_index"
```
:::{/step}
:::{step} Let Chirp track what ran
Applied migrations are recorded in a `_chirp_migrations` table. Each migration runs in its own transaction — if one fails, it rolls back without affecting the migrations before it. Running `migrate()` again only applies new files, so it is safe to call on every startup.
:::{/step}
::::{/steps}

:::{warning}
Do not write `BEGIN`, `COMMIT`, or `ROLLBACK` in a migration file. Chirp wraps each migration in its own transaction and owns the boundary; a manual statement breaks that contract.
:::

### Applied migrations are immutable

Chirp records a SHA-256 checksum of each migration's SQL when it applies it (in the `checksum` column of `_chirp_migrations`). On every run it re-hashes the on-disk file and compares. **Editing an already-applied `NNN_*.sql` file fails loud** with `MigrationError` on the next `migrate()` — naming the file, before applying anything — instead of being silently ignored forever (a real data-corruption footgun when a team "just fixes a typo").

The correct workflow when an applied migration is wrong is to **write a new forward migration** that corrects it:

```sql
-- migrations/003_add_email_index.sql
CREATE INDEX idx_users_email ON users (email);
```

:::{note}
Tracking rows written by a Chirp version older than this checksum support have a `NULL` checksum and are treated as legacy — they are skipped by the drift check, never retroactively flagged. The `checksum` column is added to an existing tracking table automatically and idempotently.
:::

## SQLite vs PostgreSQL

The only thing that changes between drivers is the connection string and the SQL placeholder style.

::::{code-tabs}
:sync: db

```python
# SQLite — built in, no extra dependency
app = App(db="sqlite:///app.db")
```

```python
# PostgreSQL — pip install bengal-chirp[data-pg]
app = App(db="postgresql://user:pass@localhost/mydb", pool_size=10)
```
::::

:::{note}
**Pick one:** SQLite gives you concurrent readers and a single serialized writer — a property of WAL, not Postgres-grade write concurrency. It is the right default for development, single-writer workloads, and small apps. Reach for PostgreSQL when multiple writers must proceed in parallel: its `asyncpg` pool runs transactions concurrently rather than behind one write lock.
:::

### Parameter style

SQLite uses `?` placeholders; PostgreSQL uses `$1`, `$2`, and so on. The mapped class and method are otherwise identical:

::::{code-tabs}
:sync: db

```python
# SQLite
await db.fetch(User, "SELECT * FROM users WHERE id = ?", 42)
```

```python
# PostgreSQL
await db.fetch(User, "SELECT * FROM users WHERE id = $1", 42)
```
::::

:::{dropdown} How SQLite and Postgres concurrency differ under the hood
:icon: cpu

For a **file-backed** SQLite database, Chirp opens a small bounded pool of WAL-mode connections sized by `pool_size`. Reads (`fetch`, `fetch_one`, `fetch_val`, `stream`) acquire any free pooled connection and run concurrently — they do not wait behind an app-wide lock. Writes (`execute`, `execute_many`, `execute_script`, and `transaction()`) serialize behind a single write lock to honor SQLite's single-writer model. An open write transaction no longer stalls reads.

**In-memory** SQLite (`sqlite:///:memory:`) is a development/test convenience and behaves differently. A private `:memory:` connection is isolated to whichever connection opened it, and shared-cache mode raises lock errors under concurrent reader/writer access. So in-memory databases use a single shared connection and serialize all access — reads included. For concurrent-reader throughput, use a file database (WAL) or PostgreSQL.

PostgreSQL has the strongest concurrency: `asyncpg` provides a real connection pool with per-transaction isolation, so reads and writes run concurrently up to `pool_size`.

For Chirp's broader free-threading posture, see [[docs/about/thread-safety|Thread Safety]].
:::{/dropdown}

:::{dropdown} Advanced: asyncpg on free-threaded Python (3.14t)
:icon: warning

Chirp's `data-pg` backend is **asyncpg** today — a Cython extension, not pure Python. Chirp talks to asyncpg directly through its own anyio-based pool shim, so Chirp does not route Postgres access through a third-party ORM or greenlet bridge. asyncpg's free-threading status remains a caveat for anyone running `bengal-chirp[data-pg]` on free-threaded builds.

Treat asyncpg-on-3.14t as best-effort: fine for development and typical OLTP workloads, but verify against the current asyncpg release notes before relying on it under heavy Postgres concurrency in production. See [[docs/about/thread-safety|Thread Safety]] for Chirp's broader free-threading posture.
:::{/dropdown}

## Real-time updates with LISTEN / NOTIFY

PostgreSQL can push notifications when a row changes. Pair `db.listen()` with [[docs/build-apps/streaming-updates/server-sent-events|Server-Sent Events]] to stream HTML the moment data changes:

```python
from chirp import EventStream, Fragment, Request

@app.route("/orders/live")
async def live_orders(request: Request) -> EventStream:
    async def generate():
        async for note in app.db.listen("new_orders"):
            order = await app.db.fetch_one(
                Order, "SELECT * FROM orders WHERE id = $1",
                int(note.payload),
            )
            if order:
                yield Fragment("orders.html", "order-row", order=order)
    return EventStream(generate())
```

On the database side, fire the notification from a trigger:

```sql
CREATE OR REPLACE FUNCTION notify_new_order()
RETURNS TRIGGER AS $$
BEGIN
    PERFORM pg_notify('new_orders', NEW.id::text);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER order_created
    AFTER INSERT ON orders
    FOR EACH ROW EXECUTE FUNCTION notify_new_order();
```

:::{note}
LISTEN/NOTIFY is a PostgreSQL feature. Calling `db.listen()` on a SQLite database raises `DataError` — SQLite has no real-time notification channel.
:::

## Error handling

All data layer errors inherit from `DataError`:

```python
from chirp.data import DataError
from chirp.data.errors import QueryError

try:
    await db.execute("INSERT INTO users ...")
except QueryError as e:
    print(f"Query failed: {e}")
```

| Error | When |
|-------|------|
| `DataError` | Base class for all data errors |
| `QueryError` | SQL execution fails |
| `DatabaseConnectionError` | Cannot connect to the database |
| `DriverNotInstalledError` | `asyncpg` is missing (install `bengal-chirp[data-pg]`) |
| `MigrationError` | A migration file is invalid or fails |

## Next Steps

- [[docs/build-apps/forms-data/shapes|Shapes]] — Bind a model class to its SQL with named placeholders and `Shape.fetch`.
- [[docs/build-apps/forms-data/forms-validation|Forms & Validation]] — Parse and validate the form data you are about to write.
- [[docs/build-apps/streaming-updates/server-sent-events|Server-Sent Events]] — Push live HTML when a row changes.
- [[docs/build-apps/request-pipeline/builtin|Built-in Middleware]] — Session middleware for per-user state.
