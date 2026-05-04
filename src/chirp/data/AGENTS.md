# Data And Schema Steward

This domain represents optional data helpers: database facade, SQLite/Postgres drivers, migrations, schema parsing/diffing/generation, pagination, and query builders.

Related docs:
- root `AGENTS.md`
- `site/content/docs/build-apps/forms-data/database.md`
- `site/content/docs/build-apps/forms-data/`
- `docs/deployment/railway.md`

## Point Of View

The app author who wants small typed data helpers without opting into an ORM, and the operator reviewing migration artifacts before deployment.

## Protect

- Data helpers stay optional; missing extras produce actionable errors.
- SQL builders keep parameters separate from generated SQL.
- Migration output is deterministic, reviewable, and safe to run intentionally.
- Pagination/query behavior is stable once documented.
- Database/shared pools have an explicit concurrency boundary.

## Contract Checklist

- Inspect driver behavior, query builders, mapping, migrations, schema diffs, pagination, optional deps, docs, examples, and changelog together.
- Update README optional extras, data docs/examples, deployment notes, and migration notes for driver/schema/query changes.
- Run `uv run pytest tests/test_data.py tests/test_query.py tests/test_query_builder.py -q`.
- Run `uv run pytest tests/test_schema.py tests/test_pagination.py -q`.
- Run `uv run pytest tests/test_concurrency/test_db_pool_stress.py -q` when pool/shared state changes.
- Run `uv run ruff check src/chirp/data`.

## Advocate

- Clearer migration previews and rollback caveats.
- Parameterized examples users can copy safely.
- More deterministic schema diff tests.

## Serve Peers

- Give `validation`, `examples`, and `site` realistic form/data flows.
- Tell `cli` when migration commands or generated artifacts change.
- Tell `security` and `cache` when data surfaces affect auth/session/cache correctness.

## Do Not

- Become an ORM or admin system.
- Make data dependencies mandatory for apps that only render HTML.
- Build SQL by unsafe string concatenation.

## Own

- `src/chirp/data/`.
- Data, query, schema, pagination, migration, and DB concurrency tests.
- Data docs, database examples, migration notes, and changelog entries for data behavior.
