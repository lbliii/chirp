"""Schema operations — the diff output that generates SQL."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CreateTable:
    """Create a new table."""

    name: str
    sql: str  # Original CREATE TABLE statement


@dataclass(frozen=True)
class DropTable:
    """Drop an existing table."""

    name: str


@dataclass(frozen=True)
class AddColumn:
    """Add a column to an existing table."""

    table: str
    name: str
    type: str
    nullable: bool = True
    default: str | None = None


@dataclass(frozen=True)
class DropColumn:
    """Drop a column from an existing table."""

    table: str
    name: str


@dataclass(frozen=True)
class CreateIndex:
    """Create a new index."""

    name: str
    table: str
    columns: tuple[str, ...]
    unique: bool = False


@dataclass(frozen=True)
class DropIndex:
    """Drop an existing index."""

    name: str


# Union of all operations
type Operation = CreateTable | DropTable | AddColumn | DropColumn | CreateIndex | DropIndex
