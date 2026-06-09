"""Schema parser — parse desired schema SQL into a SchemaSnapshot.

Parses CREATE TABLE and CREATE INDEX statements from SQL text.
"""

import re
from pathlib import Path

from chirp.data.schema.types import (
    ColumnSchema,
    ForeignKey,
    IndexSchema,
    SchemaSnapshot,
    TableSchema,
)

# Regex patterns for SQL parsing
_CREATE_TABLE_RE = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s*\((.*?)\)\s*;",
    re.IGNORECASE | re.DOTALL,
)
_CREATE_INDEX_RE = re.compile(
    r"CREATE\s+(UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)\s+"
    r"ON\s+(\w+)\s*\(([^)]+)\)\s*;",
    re.IGNORECASE,
)
_REFERENCES_RE = re.compile(
    r"REFERENCES\s+(\w+)\s*\(\s*(\w+)\s*\)",
    re.IGNORECASE,
)
_ADD_COLUMN_RE = re.compile(
    r"ALTER\s+TABLE\s+(\w+)\s+ADD\s+(?:COLUMN\s+)?(\w+)\s+(\w+)",
    re.IGNORECASE,
)


def _parse_column_def(
    col_def: str, table_name: str
) -> tuple[ColumnSchema | None, ForeignKey | None]:
    """Parse a single column definition."""
    col_def = col_def.strip()
    if not col_def:
        return None, None

    # Skip table-level constraints
    upper = col_def.upper().lstrip()
    if upper.startswith(("PRIMARY KEY", "FOREIGN KEY", "UNIQUE", "CHECK", "CONSTRAINT")):
        return None, None

    parts = col_def.split()
    if len(parts) < 2:
        return None, None

    name = parts[0].strip('"').strip("`")
    col_type = parts[1].upper()

    # Check for NOT NULL
    nullable = "NOT NULL" not in col_def.upper()

    # Check for PRIMARY KEY
    pk = "PRIMARY KEY" in col_def.upper()

    # Check for DEFAULT
    default = None
    default_match = re.search(
        r"DEFAULT\s+(.+?)(?:\s+(?:NOT|NULL|PRIMARY|REFERENCES|UNIQUE|CHECK)|$)",
        col_def,
        re.IGNORECASE,
    )
    if default_match:
        default = default_match.group(1).strip().rstrip(",")

    # Check for REFERENCES
    fk = None
    ref_match = _REFERENCES_RE.search(col_def)
    if ref_match:
        fk = ForeignKey(
            column=name,
            ref_table=ref_match.group(1),
            ref_column=ref_match.group(2),
        )

    col = ColumnSchema(
        name=name,
        type=col_type,
        nullable=nullable,
        default=default,
        primary_key=pk,
    )
    return col, fk


def _split_column_defs(body: str) -> list[str]:
    """Split column definitions handling nested parentheses."""
    result = []
    depth = 0
    current = []
    for char in body:
        if char == "(":
            depth += 1
            current.append(char)
        elif char == ")":
            depth -= 1
            current.append(char)
        elif char == "," and depth == 0:
            result.append("".join(current))
            current = []
        else:
            current.append(char)
    if current:
        result.append("".join(current))
    return result


def parse_schema(sql: str) -> SchemaSnapshot:
    """Parse SQL schema text into a SchemaSnapshot.

    Supports CREATE TABLE and CREATE INDEX statements.
    """
    tables: dict[str, TableSchema] = {}
    indexes: dict[str, IndexSchema] = {}

    # Parse CREATE TABLE statements
    for match in _CREATE_TABLE_RE.finditer(sql):
        table_name = match.group(1)
        body = match.group(2)

        columns: dict[str, ColumnSchema] = {}
        fks: list[ForeignKey] = []

        for col_def in _split_column_defs(body):
            col, fk = _parse_column_def(col_def, table_name)
            if col is not None:
                columns[col.name] = col
            if fk is not None:
                fks.append(fk)

        tables[table_name] = TableSchema(
            name=table_name,
            columns=columns,
            foreign_keys=tuple(fks),
        )

    # Parse CREATE INDEX statements
    for match in _CREATE_INDEX_RE.finditer(sql):
        unique = match.group(1) is not None
        idx_name = match.group(2)
        table_name = match.group(3)
        cols = tuple(c.strip().strip('"').strip("`") for c in match.group(4).split(","))
        indexes[idx_name] = IndexSchema(
            name=idx_name,
            table=table_name,
            columns=cols,
            unique=unique,
        )

    return SchemaSnapshot(tables=tables, indexes=indexes)


def _apply_add_columns(sql: str, tables: dict[str, TableSchema]) -> None:
    """Apply ``ALTER TABLE ... ADD COLUMN`` statements to parsed tables.

    ``parse_schema`` only models ``CREATE TABLE`` / ``CREATE INDEX``. Migrations
    routinely add columns later, so the declared-schema union used by contract
    checks must fold those in or a perfectly valid SELECT would look like drift.
    Only the column *name* matters for the shape contract; type is recorded as a
    best-effort string. Unknown tables are ignored (no CREATE seen yet).
    """
    for match in _ADD_COLUMN_RE.finditer(sql):
        table_name = match.group(1)
        col_name = match.group(2).strip('"').strip("`")
        col_type = match.group(3).upper()
        table = tables.get(table_name)
        if table is None or col_name in table.columns:
            continue
        new_columns = dict(table.columns)
        new_columns[col_name] = ColumnSchema(name=col_name, type=col_type)
        tables[table_name] = TableSchema(
            name=table.name,
            columns=new_columns,
            foreign_keys=table.foreign_keys,
        )


def schema_from_migrations(migrations_dir: str | Path) -> SchemaSnapshot | None:
    """Build a declared :class:`SchemaSnapshot` from a migrations directory.

    Reads every ``*.sql`` file in *migrations_dir* in sorted (version) order and
    folds their ``CREATE TABLE`` / ``CREATE INDEX`` / ``ALTER TABLE ADD COLUMN``
    statements into a single snapshot. This is the *declared* schema used by the
    ``data`` shape contract -- no live database connection is required.

    Returns ``None`` when the directory is missing or contains no ``.sql`` files,
    so the contract stays a silent no-op for HTML-only / db-less apps. This is a
    tolerant, static read: malformed individual statements are simply not parsed
    rather than raising (unlike the migration *runner*, which must be strict).

    Fidelity note: only ``CREATE``/``ADD COLUMN`` are folded; ``ALTER TABLE
    RENAME COLUMN`` and ``DROP COLUMN`` are *not* applied, so a heavily-altered
    table's snapshot may list columns that no longer exist. Because the ``data``
    shape contract uses this snapshot only to *suppress* drift warnings (never to
    raise on its own), an over-broad column set is the safe direction -- it can
    miss a real drift but will not invent a false positive.
    """
    path = Path(migrations_dir)
    if not path.is_dir():
        return None

    tables: dict[str, TableSchema] = {}
    indexes: dict[str, IndexSchema] = {}
    found_sql = False

    for sql_file in sorted(path.glob("*.sql")):
        try:
            sql = sql_file.read_text(encoding="utf-8")
        except OSError:
            continue
        if not sql.strip():
            continue
        found_sql = True
        snapshot = parse_schema(sql)
        tables.update(snapshot.tables)
        indexes.update(snapshot.indexes)
        _apply_add_columns(sql, tables)

    if not found_sql:
        return None
    return SchemaSnapshot(tables=tables, indexes=indexes)
