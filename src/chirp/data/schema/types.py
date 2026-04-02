"""Schema types — frozen dataclasses for schema snapshots."""

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ColumnSchema:
    """A single column in a table."""

    name: str
    type: str
    nullable: bool = True
    default: str | None = None
    primary_key: bool = False


@dataclass(frozen=True, slots=True)
class IndexSchema:
    """A database index."""

    name: str
    table: str
    columns: tuple[str, ...]
    unique: bool = False


@dataclass(frozen=True, slots=True)
class ForeignKey:
    """A foreign key constraint."""

    column: str
    ref_table: str
    ref_column: str


@dataclass(frozen=True, slots=True)
class TableSchema:
    """Schema for a single table."""

    name: str
    columns: dict[str, ColumnSchema] = field(default_factory=dict)
    foreign_keys: tuple[ForeignKey, ...] = ()


@dataclass(frozen=True, slots=True)
class SchemaSnapshot:
    """Complete database schema snapshot."""

    tables: dict[str, TableSchema] = field(default_factory=dict)
    indexes: dict[str, IndexSchema] = field(default_factory=dict)
