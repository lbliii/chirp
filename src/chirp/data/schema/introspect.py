"""Schema introspection — read current database schema into a SchemaSnapshot.

Supports SQLite and PostgreSQL.

Row access uses the documented :meth:`chirp.data.database.Database.fetch_raw`
contract: every row is a ``{column_name: value}`` dict on both backends, so
introspection reads named columns (including ``PRAGMA`` output) uniformly.
"""

from chirp.data.schema.types import (
    ColumnSchema,
    ForeignKey,
    IndexSchema,
    SchemaSnapshot,
    TableSchema,
)


async def introspect_sqlite(db) -> SchemaSnapshot:
    """Read schema from a SQLite database."""
    tables: dict[str, TableSchema] = {}
    indexes: dict[str, IndexSchema] = {}

    # Get table names
    rows = await db.fetch_raw(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )
    for row in rows:
        table_name = row["name"]

        # Get columns — PRAGMA table_info returns named columns:
        # cid, name, type, notnull, dflt_value, pk
        col_rows = await db.fetch_raw(f"PRAGMA table_info({table_name})")
        columns: dict[str, ColumnSchema] = {}
        for col in col_rows:
            columns[col["name"]] = ColumnSchema(
                name=col["name"],
                type=col["type"],
                nullable=not bool(col["notnull"]),
                default=col["dflt_value"],
                primary_key=bool(col["pk"]),
            )

        # Get foreign keys — PRAGMA foreign_key_list columns include
        # table (referenced), from (local column), to (referenced column).
        fk_rows = await db.fetch_raw(f"PRAGMA foreign_key_list({table_name})")
        fks = [
            ForeignKey(column=fk["from"], ref_table=fk["table"], ref_column=fk["to"])
            for fk in fk_rows
        ]

        tables[table_name] = TableSchema(
            name=table_name,
            columns=columns,
            foreign_keys=tuple(fks),
        )

        # Get indexes for this table — PRAGMA index_list columns: seq, name, unique, ...
        idx_rows = await db.fetch_raw(f"PRAGMA index_list({table_name})")
        for idx in idx_rows:
            idx_name = idx["name"]
            # Skip auto-indexes
            if idx_name.startswith("sqlite_"):
                continue
            # PRAGMA index_info columns: seqno, cid, name
            idx_info = await db.fetch_raw(f"PRAGMA index_info({idx_name})")
            idx_cols = [info["name"] for info in idx_info]
            indexes[idx_name] = IndexSchema(
                name=idx_name,
                table=table_name,
                columns=tuple(idx_cols),
                unique=bool(idx["unique"]),
            )

    return SchemaSnapshot(tables=tables, indexes=indexes)


async def introspect_postgres(db) -> SchemaSnapshot:
    """Read schema from a PostgreSQL database."""
    tables: dict[str, TableSchema] = {}
    indexes: dict[str, IndexSchema] = {}

    # Get tables
    rows = await db.fetch_raw(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
    )
    for row in rows:
        table_name = row["table_name"]

        # Get columns
        col_rows = await db.fetch_raw(
            "SELECT column_name, data_type, is_nullable, column_default "
            "FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = $1 "
            "ORDER BY ordinal_position",
            table_name,
        )
        columns: dict[str, ColumnSchema] = {}
        for col in col_rows:
            columns[col["column_name"]] = ColumnSchema(
                name=col["column_name"],
                type=str(col["data_type"]).upper(),
                nullable=col["is_nullable"] == "YES",
                default=col["column_default"],
            )

        tables[table_name] = TableSchema(name=table_name, columns=columns)

    return SchemaSnapshot(tables=tables, indexes=indexes)


async def introspect(db) -> SchemaSnapshot:
    """Auto-detect database backend and introspect its schema.

    Dispatches on the live :attr:`Database._driver` value
    (``"sqlite"`` or ``"postgresql"``), which is set from the connection
    URL scheme — not a guessed attribute name.
    """
    driver = getattr(db, "_driver", None)
    if driver == "postgresql":
        return await introspect_postgres(db)
    if driver == "sqlite":
        return await introspect_sqlite(db)
    msg = (
        f"introspect() does not support driver {driver!r}. "
        "Supported backends: 'sqlite', 'postgresql'."
    )
    raise ValueError(msg)
