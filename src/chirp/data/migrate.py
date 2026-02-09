"""Forward-only SQL migration runner.

Migrations are numbered ``.sql`` files in a directory::

    migrations/
        001_create_users.sql
        002_add_email_index.sql
        003_create_orders.sql

Applied migrations are tracked in a ``_chirp_migrations`` table.
Each migration runs inside a transaction — if it fails, the migration
is rolled back and no further migrations are applied.

Usage::

    from chirp.data import Database, migrate

    db = Database("sqlite:///app.db")
    await db.connect()
    await migrate(db, "migrations/")

Or integrated with the app::

    app = App(db="sqlite:///app.db", migrations="migrations/")
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from chirp.data.database import Database
from chirp.data.errors import MigrationError

_TRACKING_TABLE = "_chirp_migrations"

_CREATE_TRACKING_SQL = f"""
CREATE TABLE IF NOT EXISTS {_TRACKING_TABLE} (
    version  INTEGER PRIMARY KEY,
    name     TEXT    NOT NULL,
    applied_at TEXT  NOT NULL
)
"""


@dataclass(frozen=True, slots=True)
class Migration:
    """A single migration file."""

    version: int
    name: str
    sql: str


@dataclass(frozen=True, slots=True)
class MigrationResult:
    """Result of running migrations."""

    applied: list[str]
    already_applied: int
    total_available: int

    @property
    def summary(self) -> str:
        if not self.applied:
            return f"Already up to date ({self.already_applied} migrations applied)"
        applied_names = ", ".join(self.applied)
        return f"Applied {len(self.applied)} migration(s): {applied_names}"


def _discover_migrations(directory: str | Path) -> list[Migration]:
    """Discover and parse migration files from a directory.

    Files must match the pattern ``NNN_description.sql`` where NNN is
    a zero-padded integer version number. Files are sorted by version.
    """
    path = Path(directory)
    if not path.is_dir():
        msg = f"Migration directory does not exist: {path}"
        raise MigrationError(msg)

    migrations: list[Migration] = []
    for sql_file in sorted(path.glob("*.sql")):
        name = sql_file.stem  # e.g. "001_create_users"
        parts = name.split("_", 1)
        if len(parts) < 2:
            msg = f"Invalid migration filename: {sql_file.name} (expected NNN_description.sql)"
            raise MigrationError(msg)
        try:
            version = int(parts[0])
        except ValueError:
            msg = f"Invalid migration version in {sql_file.name}: {parts[0]!r} is not an integer"
            raise MigrationError(msg) from None

        sql = sql_file.read_text(encoding="utf-8").strip()
        if not sql:
            msg = f"Empty migration file: {sql_file.name}"
            raise MigrationError(msg)

        migrations.append(Migration(version=version, name=name, sql=sql))

    # Check for duplicate versions
    versions = [m.version for m in migrations]
    if len(versions) != len(set(versions)):
        msg = "Duplicate migration version numbers found"
        raise MigrationError(msg)

    return migrations


async def _ensure_tracking_table(db: Database) -> None:
    """Create the migration tracking table if it doesn't exist."""
    await db.execute(_CREATE_TRACKING_SQL)


async def _get_applied_versions(db: Database) -> set[int]:
    """Get the set of already-applied migration versions."""

    @dataclass(frozen=True, slots=True)
    class _Version:
        version: int

    rows = await db.fetch(_Version, f"SELECT version FROM {_TRACKING_TABLE}")
    return {row.version for row in rows}


async def _apply_migration(db: Database, migration: Migration) -> None:
    """Apply a single migration.

    Uses ``execute_script`` for SQLite to support multi-statement migration
    files (e.g. CREATE TABLE + CREATE INDEX in one file). The tracking
    record is inserted separately after the migration succeeds.
    """
    now = datetime.now(UTC).isoformat()
    await db.execute_script(migration.sql)
    await db.execute(
        f"INSERT INTO {_TRACKING_TABLE} (version, name, applied_at) VALUES (?, ?, ?)",
        migration.version,
        migration.name,
        now,
    )


async def migrate(db: Database, directory: str | Path) -> MigrationResult:
    """Apply pending migrations from a directory.

    Discovers ``.sql`` files, compares against the tracking table,
    and applies missing migrations in version order. Each migration
    runs in its own transaction.

    Args:
        db: Connected database instance.
        directory: Path to the migrations directory.

    Returns:
        MigrationResult with details of what was applied.

    Raises:
        MigrationError: If a migration fails or the directory is invalid.
    """
    migrations = _discover_migrations(directory)
    await _ensure_tracking_table(db)
    applied_versions = await _get_applied_versions(db)

    pending = [m for m in migrations if m.version not in applied_versions]
    pending.sort(key=lambda m: m.version)

    applied_names: list[str] = []
    for migration in pending:
        try:
            await _apply_migration(db, migration)
            applied_names.append(migration.name)
        except Exception as exc:
            msg = f"Migration {migration.name} failed: {exc}"
            raise MigrationError(msg) from exc

    return MigrationResult(
        applied=applied_names,
        already_applied=len(applied_versions),
        total_available=len(migrations),
    )
