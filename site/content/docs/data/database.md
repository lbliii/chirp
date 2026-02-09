---
title: Database
description: Async database access with SQLite and PostgreSQL
draft: false
weight: 10
lang: en
type: doc
tags: [database, sqlite, postgresql, async]
keywords: [database, sqlite, postgresql, aiosqlite, asyncpg, query, row-mapping, transactions, migrations]
category: guide
---

## Overview

Chirp's `data` module provides typed async database access. SQL in, frozen dataclasses out. It is not an ORM -- you write SQL, and chirp maps the results to typed Python objects.

:::{note}
Requires optional extras: `pip install bengal-chirp[data]` for SQLite or `pip install bengal-chirp[data-pg]` for PostgreSQL.
:::

## Setup

### App Integration

The simplest setup -- pass a connection URL to `App()`:

```python
from chirp import App

app = App(db="sqlite:///app.db")
```

The database connects on startup and disconnects on shutdown automatically. Access it via `app.db`:

```python
@app.route("/users")
async def list_users():
    users = await app.db.fetch(User, "SELECT * FROM users")
    return Template("users.html", users=users)
```

You can also pass a `Database` instance for more control:

```python
from chirp.data import Database

db = Database("postgresql://user:pass@localhost/mydb", pool_size=10)
app = App(db=db)
```

### Standalone Usage

Use `Database` directly without the app:

```python
from chirp.data import Database

db = Database("sqlite:///app.db")
await db.connect()

# ... use db ...

await db.disconnect()
```

Or as an async context manager:

```python
async with Database("sqlite:///app.db") as db:
    users = await db.fetch(User, "SELECT * FROM users")
```

### `get_db()` Accessor

When using `App(db=...)`, the database is available from any handler via `get_db()`:

```python
from chirp.data import get_db

@app.route("/users")
async def list_users():
    db = get_db()
    users = await db.fetch(User, "SELECT * FROM users")
    return Template("users.html", users=users)
```

## Data Models

Define frozen dataclasses that match your query columns:

```python
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class User:
    id: int
    name: str
    email: str
```

Query results are mapped to these dataclasses automatically. Extra columns are silently ignored -- `SELECT *` works even if the dataclass has fewer fields.

## Query Methods

### `fetch` -- All Rows

```python
users = await db.fetch(User, "SELECT * FROM users WHERE active = ?", True)
# Returns: list[User]
```

### `fetch_one` -- Single Row

```python
user = await db.fetch_one(User, "SELECT * FROM users WHERE id = ?", 42)
# Returns: User | None
```

### `fetch_val` -- Scalar Value

```python
count = await db.fetch_val("SELECT COUNT(*) FROM users")
# Returns: Any

count = await db.fetch_val("SELECT COUNT(*) FROM users", as_type=int)
# Returns: int | None
```

### `execute` -- INSERT / UPDATE / DELETE

```python
rows_affected = await db.execute(
    "INSERT INTO users (name, email) VALUES (?, ?)",
    "Alice", "alice@example.com",
)
# Returns: int (rows affected)
```

### `execute_many` -- Batch Operations

```python
await db.execute_many(
    "INSERT INTO users (name, email) VALUES (?, ?)",
    [("Alice", "a@b.com"), ("Bob", "b@b.com"), ("Carol", "c@b.com")],
)
```

### `stream` -- Cursor-Based Iteration

For large result sets, stream rows without loading everything into memory:

```python
async for user in db.stream(User, "SELECT * FROM users", batch_size=100):
    process(user)
```

### Reference

| Method | Returns | Description |
|--------|---------|-------------|
| `fetch(cls, sql, *params)` | `list[T]` | All matching rows as dataclasses |
| `fetch_one(cls, sql, *params)` | `T \| None` | First row or None |
| `fetch_val(sql, *params)` | `Any` | First column of first row |
| `execute(sql, *params)` | `int` | Rows affected |
| `execute_many(sql, params_seq)` | `int` | Total rows affected |
| `stream(cls, sql, *params)` | `AsyncIterator[T]` | Cursor-based row iteration |

## Transactions

Wrap multiple statements in an atomic transaction:

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

Auto-commits on clean exit, auto-rolls back on exception:

```python
async with db.transaction():
    await db.execute("INSERT INTO users ...", name, email)
    raise ValueError("something went wrong")
    # everything rolled back -- nothing committed
```

Reads inside a transaction see uncommitted writes:

```python
async with db.transaction():
    await db.execute("INSERT INTO users (name, email) VALUES (?, ?)", "Alice", "a@b.com")
    count = await db.fetch_val("SELECT COUNT(*) FROM users")
    # count includes the uncommitted row
```

Nesting is transparent -- inner `transaction()` joins the outer one:

```python
async with db.transaction():
    await db.execute("INSERT INTO users ...", name, email)
    async with db.transaction():  # no-op, joins outer
        await db.execute("INSERT INTO profiles ...", user_id)
    # both committed together
```

## Migrations

Forward-only SQL migrations. Create numbered `.sql` files in a directory:

```
migrations/
    001_create_users.sql
    002_add_email_index.sql
    003_create_orders.sql
```

### With the App

```python
app = App(db="sqlite:///app.db", migrations="migrations/")
```

Pending migrations run automatically at startup. Each migration runs in its own transaction -- if one fails, it rolls back without affecting previously applied migrations.

### Standalone

```python
from chirp.data import Database, migrate

db = Database("sqlite:///app.db")
await db.connect()

result = await migrate(db, "migrations/")
print(result.summary)
# "Applied 2 migration(s): 001_create_users, 002_add_email_index"
```

### Tracking

Applied migrations are tracked in a `_chirp_migrations` table. Running `migrate()` again only applies new migrations -- it is safe to call on every startup.

### Migration Files

Each file is plain SQL executed as a single statement:

```sql
-- migrations/001_create_users.sql
CREATE TABLE users (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name  TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE
)
```

Naming convention: `NNN_description.sql` where `NNN` is a zero-padded version number.

## Echo / Query Logging

Enable SQL logging to see every query with timing:

```python
db = Database("sqlite:///app.db", echo=True)
```

Output goes to stderr:

```
[chirp.data]    0.3ms  SELECT * FROM users WHERE active = ?  params=(True,)
[chirp.data]    0.1ms  INSERT INTO users (name, email) VALUES (?, ?)  params=('Alice', 'alice@example.com')
```

## LISTEN / NOTIFY (PostgreSQL)

Listen for real-time database notifications:

```python
async for notification in db.listen("new_orders"):
    print(f"Channel: {notification.channel}")
    print(f"Payload: {notification.payload}")
```

Pair with chirp's `EventStream` for real-time HTML updates:

```python
from chirp import EventStream, Fragment

@app.route("/orders/live")
async def live_orders(request):
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

On the PostgreSQL side, trigger notifications from a function or manually:

```sql
-- Trigger on INSERT
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
LISTEN/NOTIFY is a PostgreSQL feature. SQLite does not support real-time notifications -- calling `db.listen()` on a SQLite database raises `DataError`.
:::

## PostgreSQL

Swap the connection string for PostgreSQL:

```python
app = App(db="postgresql://user:pass@localhost/mydb")
```

PostgreSQL uses `asyncpg` with connection pooling. Configure pool size:

```python
from chirp.data import Database

db = Database("postgresql://user:pass@localhost/mydb", pool_size=10)
app = App(db=db)
```

:::{note}
PostgreSQL requires the `data-pg` extra: `pip install bengal-chirp[data-pg]`. This installs `asyncpg`.
:::

### Parameter Style

SQLite uses `?` placeholders. PostgreSQL uses `$1`, `$2`, etc:

```python
# SQLite
await db.fetch(User, "SELECT * FROM users WHERE id = ?", 42)

# PostgreSQL
await db.fetch(User, "SELECT * FROM users WHERE id = $1", 42)
```

## Error Handling

All data layer errors inherit from `DataError`:

| Error | When |
|-------|------|
| `DataError` | Base class for all data errors |
| `QueryError` | SQL execution fails |
| `ConnectionError` | Cannot connect to database |
| `DriverNotInstalledError` | Missing `aiosqlite` or `asyncpg` |
| `MigrationError` | Migration file invalid or execution fails |

```python
from chirp.data import DataError
from chirp.data.errors import QueryError

try:
    await db.execute("INSERT INTO users ...")
except QueryError as e:
    print(f"Query failed: {e}")
```

## Next Steps

- [[docs/data/forms-validation|Forms & Validation]] -- Parse and validate form data
- [[docs/streaming/sse|Server-Sent Events]] -- Real-time updates with SSE
- [[docs/middleware/builtin|Built-in Middleware]] -- Session middleware for user state
