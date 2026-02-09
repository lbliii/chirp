---
title: Database
description: Async database access with SQLite and PostgreSQL
draft: false
weight: 10
lang: en
type: doc
tags: [database, sqlite, postgresql, async]
keywords: [database, sqlite, postgresql, aiosqlite, asyncpg, query, row-mapping]
category: guide
---

## Overview

Chirp's `data` module provides a lightweight async database interface. It is not an ORM -- it is a thin wrapper around async database drivers with typed row mapping.

:::{note}
Requires optional extras: `pip install bengal-chirp[data]` for SQLite or `pip install bengal-chirp[data-pg]` for PostgreSQL.
:::

## Setup

Connect to a database during app startup:

```python
from chirp.data import Database

@app.on_startup
async def connect_db():
    app.db = await Database.connect("sqlite:///app.db")

@app.on_shutdown
async def close_db():
    await app.db.close()
```

## Queries

Execute queries with parameter binding:

```python
@app.route("/users")
async def list_users():
    rows = await app.db.fetch_all("SELECT id, name, email FROM users")
    return Template("users.html", users=rows)

@app.route("/users/{id:int}")
async def get_user(id: int):
    row = await app.db.fetch_one(
        "SELECT id, name, email FROM users WHERE id = ?", [id]
    )
    if not row:
        raise NotFound(f"User {id} not found")
    return Template("user.html", user=row)
```

### Query Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `fetch_all(sql, params)` | `list[Row]` | All matching rows |
| `fetch_one(sql, params)` | `Row \| None` | First matching row |
| `execute(sql, params)` | `int` | Affected row count |

## Row Mapping

Map rows to dataclasses for type safety:

```python
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class User:
    id: int
    name: str
    email: str

@app.route("/users")
async def list_users():
    rows = await app.db.fetch_all("SELECT id, name, email FROM users")
    users = [User(**row) for row in rows]
    return Template("users.html", users=users)
```

The `data` module includes a `_mapping` module that can automate this mapping from query results to dataclass instances.

## Transactions

```python
@app.route("/transfer", methods=["POST"])
async def transfer(request: Request):
    data = await request.json()
    async with app.db.transaction():
        await app.db.execute(
            "UPDATE accounts SET balance = balance - ? WHERE id = ?",
            [data["amount"], data["from_id"]],
        )
        await app.db.execute(
            "UPDATE accounts SET balance = balance + ? WHERE id = ?",
            [data["amount"], data["to_id"]],
        )
    return {"status": "ok"}
```

## PostgreSQL

Swap the connection string for PostgreSQL support:

```python
@app.on_startup
async def connect_db():
    app.db = await Database.connect("postgresql://user:pass@localhost/mydb")
```

:::{note}
PostgreSQL requires the `data-pg` extra: `pip install bengal-chirp[data-pg]`. This installs `asyncpg`.
:::

## Next Steps

- [[docs/data/forms-validation|Forms & Validation]] -- Parse and validate form data
- [[docs/middleware/builtin|Built-in Middleware]] -- Session middleware for user state
- [[docs/reference/api|API Reference]] -- Complete API surface
