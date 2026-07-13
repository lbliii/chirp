<!-- generated from .stewards/manifest.toml — edit the manifest, not this file -->

# Steward: data

Keep typed data helpers, parameterized queries, deterministic schema diffs, migrations, and pools useful without becoming an ORM.

Ordinary work: use this map directly with the root map and run only affected checks.
Do not open `.stewards/PROTOCOL.md` or `.stewards/manifest.toml` unless the task is an explicit review/audit or steward-network maintenance.

## Protects

| Invariant | Sev | Backing | Proof / anchor |
| --- | --- | --- | --- |
| Database, query, schema, migration, pagination, and mapping helpers retain deterministic typed behavior. | P1 | machine-backed | `uv run pytest tests/test_data.py tests/test_query.py tests/test_query_builder.py tests/test_schema.py tests/test_pagination.py -q` (`data-suite`) |

## Guardrails

- Postgres support and drivers remain optional.
- Generated migrations remain deterministic and reviewable.
- Shared pools have explicit concurrency boundaries.

## Edges

- adapts → **pelt** (in-tree PostgreSQL driver)
- exposed-by → **cli** (migration commands)

## Owns

- **code:** `src/chirp/data/`
- **tests:** `tests/test_data.py`, `tests/test_query.py`, `tests/test_schema.py`
- **docs:** `docs/deployment/railway.md`
