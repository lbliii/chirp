"""Migration file generator — Operations to numbered .sql files."""

import re
from pathlib import Path

from chirp.data.schema.operations import (
    AddColumn,
    CreateIndex,
    CreateTable,
    DropColumn,
    DropIndex,
    DropTable,
    Operation,
)


def operation_to_sql(op: Operation) -> str:
    """Convert a single operation to SQL."""
    match op:
        case CreateTable(name=_, sql=sql):
            return f"{sql};"
        case DropTable(name=name):
            return f"DROP TABLE {name};"
        case AddColumn(table=table, name=name, type=type_, nullable=nullable, default=default):
            parts = [f"ALTER TABLE {table} ADD COLUMN {name} {type_}"]
            if not nullable:
                parts.append("NOT NULL")
            if default is not None:
                parts.append(f"DEFAULT {default}")
            return " ".join(parts) + ";"
        case DropColumn(table=table, name=name):
            return f"ALTER TABLE {table} DROP COLUMN {name};"
        case CreateIndex(name=name, table=table, columns=columns, unique=unique):
            u = "UNIQUE " if unique else ""
            cols = ", ".join(columns)
            return f"CREATE {u}INDEX {name} ON {table} ({cols});"
        case DropIndex(name=name):
            return f"DROP INDEX {name};"
        case _:
            msg = f"Unknown operation: {op}"
            raise ValueError(msg)


def _next_migration_number(migrations_dir: str) -> int:
    """Find the next migration number by scanning existing files."""
    path = Path(migrations_dir)
    if not path.exists():
        return 1
    existing = []
    for f in path.iterdir():
        if f.suffix == ".sql":
            match = re.match(r"^(\d+)", f.name)
            if match:
                existing.append(int(match.group(1)))
    return max(existing, default=0) + 1


def _slugify(ops: list[Operation]) -> str:
    """Generate a slug from operations for the migration filename."""
    if not ops:
        return "empty"
    parts = []
    for op in ops[:3]:  # Limit to 3 for filename sanity
        match op:
            case CreateTable(name=name):
                parts.append(f"create_{name}")
            case DropTable(name=name):
                parts.append(f"drop_{name}")
            case AddColumn(table=table, name=name):
                parts.append(f"add_{table}_{name}")
            case DropColumn(table=table, name=name):
                parts.append(f"drop_{table}_{name}")
            case CreateIndex(name=name):
                parts.append(f"create_idx_{name}")
            case DropIndex(name=name):
                parts.append(f"drop_idx_{name}")
    if len(ops) > 3:
        parts.append("and_more")
    return "_".join(parts)


def generate_migration(
    ops: list[Operation],
    migrations_dir: str = "migrations",
) -> str | None:
    """Generate a numbered .sql migration file from operations.

    Returns the path to the generated file, or None if no operations.
    """
    if not ops:
        return None

    path = Path(migrations_dir)
    path.mkdir(parents=True, exist_ok=True)

    num = _next_migration_number(migrations_dir)
    slug = _slugify(ops)
    filename = f"{num:03d}_{slug}.sql"
    filepath = path / filename

    lines = [f"-- Migration {num:03d}: {slug}", "--"]
    lines.extend(operation_to_sql(op) for op in ops)
    lines.append("")

    filepath.write_text("\n".join(lines))
    return str(filepath)
