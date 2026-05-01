# AGENTS.md

## Steward: Data And Schema Steward

This domain protects optional data helpers: database facade, SQLite/Postgres drivers, migrations,
schema parsing/diffing/generation, pagination, and query builders.

## Must Not Become

- An ORM or admin system.
- A mandatory dependency path for apps that only render HTML.
- A string-concatenation SQL layer that defeats parameterization.

## Documentation Ownership

Update README optional extras, data docs/examples, changelog, and migration notes when driver,
schema, or query behavior changes.

## Local Checks

Start with:

- `uv run pytest tests/test_data.py tests/test_query.py tests/test_query_builder.py -q`
- `uv run pytest tests/test_schema.py tests/test_pagination.py -q`
- `uv run ruff check src/chirp/data`

## Public Contracts And Safety Boundaries

- Data helpers are optional; missing extras need actionable errors.
- SQL builders must keep parameters separate from generated SQL.
- Migration output is a public artifact; keep it deterministic and reviewable.
