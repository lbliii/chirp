"""Schema diff — compare two SchemaSnapshots and produce Operations."""

from chirp.data.schema.operations import (
    AddColumn,
    CreateIndex,
    CreateTable,
    DropColumn,
    DropIndex,
    DropTable,
    Operation,
)
from chirp.data.schema.types import SchemaSnapshot


def diff_schemas(current: SchemaSnapshot, desired: SchemaSnapshot) -> list[Operation]:
    """Compare current and desired schemas, returning operations to migrate.

    Operations are ordered: drops first, then creates, then alters.
    """
    ops: list[Operation] = []

    current_tables = set(current.tables)
    desired_tables = set(desired.tables)

    # Tables to drop (in current but not desired)
    ops.extend(DropTable(name=name) for name in sorted(current_tables - desired_tables))

    # Tables to create (in desired but not current)
    for name in sorted(desired_tables - current_tables):
        table = desired.tables[name]
        # Build CREATE TABLE SQL
        col_defs = []
        for col in table.columns.values():
            parts = [col.name, col.type]
            if col.primary_key:
                parts.append("PRIMARY KEY")
            if not col.nullable:
                parts.append("NOT NULL")
            if col.default is not None:
                parts.append(f"DEFAULT {col.default}")
            col_defs.append(" ".join(parts))
        col_defs.extend(
            f"FOREIGN KEY ({fk.column}) REFERENCES {fk.ref_table}({fk.ref_column})"
            for fk in table.foreign_keys
        )
        sql = f"CREATE TABLE {name} (\n    " + ",\n    ".join(col_defs) + "\n)"
        ops.append(CreateTable(name=name, sql=sql))

    # Column changes for existing tables
    for name in sorted(current_tables & desired_tables):
        current_cols = set(current.tables[name].columns)
        desired_cols = set(desired.tables[name].columns)

        # Drop removed columns
        ops.extend(
            DropColumn(table=name, name=col_name)
            for col_name in sorted(current_cols - desired_cols)
        )

        # Add new columns
        for col_name in sorted(desired_cols - current_cols):
            col = desired.tables[name].columns[col_name]
            ops.append(
                AddColumn(
                    table=name,
                    name=col_name,
                    type=col.type,
                    nullable=col.nullable,
                    default=col.default,
                )
            )

    # Index changes
    current_idxs = set(current.indexes)
    desired_idxs = set(desired.indexes)

    ops.extend(DropIndex(name=idx_name) for idx_name in sorted(current_idxs - desired_idxs))

    for idx_name in sorted(desired_idxs - current_idxs):
        idx = desired.indexes[idx_name]
        ops.append(
            CreateIndex(
                name=idx_name,
                table=idx.table,
                columns=idx.columns,
                unique=idx.unique,
            )
        )

    return ops
