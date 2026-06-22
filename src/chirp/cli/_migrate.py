"""Apply pending schema migrations CLI command.

``chirp migrate --db sqlite:///app.db --migrations-dir migrations``

Symmetric with the sibling ``chirp makemigrations`` (same ``--db`` /
``--migrations-dir`` flag surface). This is a one-shot job: it connects to the
database, applies pending migrations via :func:`chirp.data.migrate.migrate`,
and disconnects. It does **not** boot the full App (no freeze, no contract
checks) — multi-instance deploys (Railway/K8s) run this as a pre-deploy job so
replicas do not race on startup migrations.

Fail-loud: a :class:`chirp.data.errors.MigrationError` (a failed migration,
an invalid migrations directory, or a checksum-drift edit of a shipped
migration) is reported and exits ``1``. Nothing is swallowed.
"""


def run_migrate(args) -> None:
    """Apply pending migrations from a directory."""
    import asyncio

    asyncio.run(_run(args))


async def _run(args) -> None:
    import sys

    from chirp.data.database import Database
    from chirp.data.errors import MigrationError
    from chirp.data.migrate import migrate

    db_url = args.db
    migrations_dir = getattr(args, "migrations_dir", "migrations")

    db = Database(db_url)
    await db.connect()
    try:
        result = await migrate(db, migrations_dir)
    except MigrationError as exc:
        print(f"Migration failed: {exc}")
        sys.exit(1)
    finally:
        await db.disconnect()

    print(result.summary)
