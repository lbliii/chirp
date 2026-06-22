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

import contextlib
import hashlib
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
    applied_at TEXT  NOT NULL,
    checksum TEXT
)
"""


def _checksum(sql: str) -> str:
    """Stable content hash of a migration's SQL body.

    Hashes the already-``.strip()``-ed ``Migration.sql`` exactly as stored at
    apply time so the drift recompute matches byte-for-byte (a whitespace or
    normalization mismatch would be a false-positive drift error).
    """
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()


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
    seen: set[int] = set()
    for m in migrations:
        if m.version in seen:
            msg = f"Duplicate migration version: {m.version} ({m.name})"
            raise MigrationError(msg)
        seen.add(m.version)

    return migrations


async def _ensure_tracking_table(db: Database) -> None:
    """Create the migration tracking table if it doesn't exist.

    Also brings a tracking table created by a pre-checksum Chirp version up to
    date: ``CREATE TABLE IF NOT EXISTS`` never alters an existing table, so the
    nullable ``checksum`` column is added idempotently here. Existing rows get
    ``NULL`` (legacy → skip-verify). Column existence is introspected per driver
    so the ``ALTER`` only runs when the column is genuinely absent — no broad
    exception swallowing.
    """
    await db.execute(_CREATE_TRACKING_SQL)
    if not await _tracking_has_checksum_column(db):
        await db.execute(f"ALTER TABLE {_TRACKING_TABLE} ADD COLUMN checksum TEXT")


async def _tracking_has_checksum_column(db: Database) -> bool:
    """Report whether the tracking table already has a ``checksum`` column."""

    @dataclass(frozen=True, slots=True)
    class _Column:
        name: str

    if getattr(db, "_driver", None) == "sqlite":
        rows = await db.fetch(_Column, f"SELECT name FROM pragma_table_info('{_TRACKING_TABLE}')")
        return any(row.name == "checksum" for row in rows)

    rows = await db.fetch(
        _Column,
        "SELECT column_name AS name FROM information_schema.columns "
        "WHERE table_name = ? AND column_name = ?",
        _TRACKING_TABLE,
        "checksum",
    )
    return bool(rows)


async def _get_applied_versions(db: Database) -> dict[int, tuple[str | None, str | None]]:
    """Get applied migrations as ``version -> (name, checksum)``.

    ``checksum`` is ``None`` for rows written before the checksum column existed
    (legacy → skipped by the drift guard).
    """

    @dataclass(frozen=True, slots=True)
    class _Row:
        version: int
        name: str | None
        checksum: str | None

    rows = await db.fetch(_Row, f"SELECT version, name, checksum FROM {_TRACKING_TABLE}")
    return {row.version: (row.name, row.checksum) for row in rows}


async def _apply_migration(db: Database, migration: Migration) -> None:
    """Apply a single migration.

    Uses ``execute_script`` for multi-statement migration files (e.g.
    CREATE TABLE + CREATE INDEX in one file). SQLite gets an explicit
    BEGIN/COMMIT wrapper because ``sqlite3.executescript`` does not honor
    the connection's surrounding transaction mode.
    """
    now = datetime.now(UTC).isoformat()
    checksum = _checksum(migration.sql)
    if getattr(db, "_driver", None) == "sqlite":
        migration_sql = migration.sql.rstrip()
        if not migration_sql.endswith(";"):
            migration_sql += ";"
        script = (
            "BEGIN;\n"
            f"{migration_sql}\n"
            f"INSERT INTO {_TRACKING_TABLE} (version, name, applied_at, checksum) "
            f"VALUES ({migration.version}, {_sql_literal(migration.name)}, "
            f"{_sql_literal(now)}, {_sql_literal(checksum)});\n"
            "COMMIT;"
        )
        # Pin one connection so the script's BEGIN/COMMIT and the failure-path
        # ROLLBACK run on the *same* pooled connection. Without the pin the
        # ROLLBACK could land on a different connection (a no-op) while the one
        # that ran the failed BEGIN is returned to the pool mid-transaction.
        async with db._pinned_connection():
            try:
                await db.execute_script(script)
            except Exception:
                with contextlib.suppress(Exception):
                    await db.execute("ROLLBACK")
                raise
        return

    async with db.transaction():
        await db.execute_script(migration.sql)
        await db.execute(
            f"INSERT INTO {_TRACKING_TABLE} (version, name, applied_at, checksum) "
            "VALUES (?, ?, ?, ?)",
            migration.version,
            migration.name,
            now,
            checksum,
        )


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


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
    applied = await _get_applied_versions(db)

    # Drift guard: an already-applied migration whose on-disk SQL no longer
    # matches the checksum recorded at apply time has been edited in place — a
    # silent data-corruption footgun. Fail loud before applying anything. A
    # NULL recorded checksum is a legacy row (written before the checksum
    # column existed) and is skipped.
    for migration in migrations:
        record = applied.get(migration.version)
        if record is None:
            continue
        _, recorded_checksum = record
        if recorded_checksum is None:
            continue
        if recorded_checksum != _checksum(migration.sql):
            msg = (
                f"Migration {migration.name} has been modified after it was applied "
                f"(on-disk SQL no longer matches the recorded checksum). Applied "
                f"migrations are immutable: write a new forward migration instead of "
                f"editing {migration.name}.sql."
            )
            raise MigrationError(msg)

    pending = [m for m in migrations if m.version not in applied]
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
        already_applied=len(applied),
        total_available=len(migrations),
    )
