"""Typed async database access for chirp.

SQL in, frozen dataclasses out. Not an ORM.

Basic usage::

    from chirp.data import Database

    db = Database("sqlite:///app.db")

    @dataclass(frozen=True, slots=True)
    class User:
        id: int
        name: str
        email: str

    users = await db.fetch(User, "SELECT * FROM users WHERE active = ?", True)
    user = await db.fetch_one(User, "SELECT * FROM users WHERE id = ?", 42)

Requires ``aiosqlite`` (for SQLite) or ``asyncpg`` (for PostgreSQL)::

    pip install chirp[data]       # SQLite
    pip install chirp[data-pg]    # PostgreSQL
"""

from chirp.data.database import Database, get_db
from chirp.data.errors import DataError, DriverNotInstalledError

__all__ = [
    "DataError",
    "Database",
    "DriverNotInstalledError",
    "get_db",
]
