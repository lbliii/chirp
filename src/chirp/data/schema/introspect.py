"""Schema introspection — read current database schema into a SchemaSnapshot.

Supports SQLite and PostgreSQL.
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
    rows = await db.fetch_rows(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )
    for row in rows:
        table_name = row[0] if isinstance(row, (list, tuple)) else row["name"]

        # Get columns
        col_rows = await db.fetch_rows(f"PRAGMA table_info({table_name})")
        columns: dict[str, ColumnSchema] = {}
        for col in col_rows:
            if isinstance(col, (list, tuple)):
                _cid, name, ctype, notnull, dflt, pk = col[:6]
            else:
                name = col["name"]
                ctype = col["type"]
                notnull = col["notnull"]
                dflt = col["dflt_value"]
                pk = col["pk"]
            columns[name] = ColumnSchema(
                name=name,
                type=ctype,
                nullable=not bool(notnull),
                default=dflt,
                primary_key=bool(pk),
            )

        # Get foreign keys
        fk_rows = await db.fetch_rows(f"PRAGMA foreign_key_list({table_name})")
        fks = []
        for fk in fk_rows:
            if isinstance(fk, (list, tuple)):
                _, _, ref_table, col_name, ref_col = fk[:5]
            else:
                ref_table = fk["table"]
                col_name = fk["from"]
                ref_col = fk["to"]
            fks.append(ForeignKey(column=col_name, ref_table=ref_table, ref_column=ref_col))

        tables[table_name] = TableSchema(
            name=table_name,
            columns=columns,
            foreign_keys=tuple(fks),
        )

        # Get indexes for this table
        idx_rows = await db.fetch_rows(f"PRAGMA index_list({table_name})")
        for idx in idx_rows:
            if isinstance(idx, (list, tuple)):
                _, idx_name, is_unique = idx[:3]
            else:
                idx_name = idx["name"]
                is_unique = idx["unique"]
            # Skip auto-indexes
            if idx_name.startswith("sqlite_"):
                continue
            idx_info = await db.fetch_rows(f"PRAGMA index_info({idx_name})")
            idx_cols = []
            for info in idx_info:
                if isinstance(info, (list, tuple)):
                    idx_cols.append(info[2])
                else:
                    idx_cols.append(info["name"])
            indexes[idx_name] = IndexSchema(
                name=idx_name,
                table=table_name,
                columns=tuple(idx_cols),
                unique=bool(is_unique),
            )

    return SchemaSnapshot(tables=tables, indexes=indexes)


async def introspect_postgres(db) -> SchemaSnapshot:
    """Read schema from a PostgreSQL database."""
    tables: dict[str, TableSchema] = {}
    indexes: dict[str, IndexSchema] = {}

    # Get tables
    rows = await db.fetch_rows(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
    )
    for row in rows:
        table_name = row[0] if isinstance(row, (list, tuple)) else row["table_name"]

        # Get columns
        col_rows = await db.fetch_rows(
            "SELECT column_name, data_type, is_nullable, column_default "
            "FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = $1 "
            "ORDER BY ordinal_position",
            table_name,
        )
        columns: dict[str, ColumnSchema] = {}
        for col in col_rows:
            if isinstance(col, (list, tuple)):
                name, ctype, nullable, default = col[:4]
            else:
                name = col["column_name"]
                ctype = col["data_type"]
                nullable = col["is_nullable"]
                default = col["column_default"]
            columns[name] = ColumnSchema(
                name=name,
                type=ctype.upper(),
                nullable=nullable == "YES",
                default=default,
            )

        tables[table_name] = TableSchema(name=table_name, columns=columns)

    return SchemaSnapshot(tables=tables, indexes=indexes)


async def introspect(db) -> SchemaSnapshot:
    """Auto-detect database type and introspect schema."""
    driver = getattr(db, "_driver_name", None) or ""
    if "postgres" in driver.lower() or "pg" in driver.lower():
        return await introspect_postgres(db)
    return await introspect_sqlite(db)
