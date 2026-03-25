"""Auto-generate schema migrations CLI command.

``chirp makemigrations --db sqlite:///app.db --schema schema.py``
"""

import importlib.util
import sys
from pathlib import Path


def run_makemigrations(args) -> None:
    """Generate migration from schema diff."""
    import asyncio

    asyncio.run(_run(args))


async def _run(args) -> None:
    from chirp.data.database import Database
    from chirp.data.schema import diff_schemas, generate_migration, introspect, parse_schema

    db_url = args.db
    schema_file = args.schema
    migrations_dir = getattr(args, "migrations_dir", "migrations")

    # Load desired schema SQL from file
    schema_path = Path(schema_file)
    if not schema_path.exists():
        print(f"Schema file not found: {schema_file}")
        sys.exit(1)

    # Try to import as Python module first (look for SCHEMA variable)
    sql_text = None
    if schema_path.suffix == ".py":
        spec = importlib.util.spec_from_file_location("_schema", schema_path)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            sql_text = getattr(mod, "SCHEMA", None)

    if sql_text is None:
        sql_text = schema_path.read_text()

    if not sql_text.strip():
        print("Schema file is empty")
        sys.exit(1)

    # Parse desired schema
    desired = parse_schema(sql_text)

    # Introspect current database
    db = Database(db_url)
    await db.connect()
    try:
        current = await introspect(db)
    finally:
        await db.disconnect()

    # Diff
    ops = diff_schemas(current, desired)
    if not ops:
        print("No changes detected.")
        return

    # Generate migration file
    filepath = generate_migration(ops, migrations_dir)
    print(f"Generated: {filepath}")
    for op in ops:
        from chirp.data.schema.generate import operation_to_sql

        print(f"  {operation_to_sql(op)}")
