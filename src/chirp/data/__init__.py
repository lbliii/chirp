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

SQLite works out of the box. For PostgreSQL, install the driver::

    pip install chirp[data-pg]    # PostgreSQL
"""

from chirp.data.database import Database, Notification, get_db
from chirp.data.errors import (
    DatabaseConnectionError,
    DataError,
    DriverNotInstalledError,
    MigrationError,
    QueryError,
    ShapeError,
)
from chirp.data.migrate import migrate
from chirp.data.pagination import PageResult
from chirp.data.query import Query, json_path
from chirp.data.shapes import (
    Composite,
    NestedShape,
    Shape,
    composite,
    nested,
    register_shape,
    shape,
    shape_registry,
)

__all__ = [
    "Composite",
    "DataError",
    "Database",
    "DatabaseConnectionError",
    "DriverNotInstalledError",
    "MigrationError",
    "NestedShape",
    "Notification",
    "PageResult",
    "Query",
    "QueryError",
    "Shape",
    "ShapeError",
    "composite",
    "get_db",
    "json_path",
    "migrate",
    "nested",
    "register_shape",
    "shape",
    "shape_registry",
]
