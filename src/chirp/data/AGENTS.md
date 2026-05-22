# Steward: Data And Schema

You keep data helpers useful without turning Chirp into an ORM. This optional
domain owns the database facade, SQLite/Postgres drivers, migrations, schema
diffing/generation, pagination, and query builders.

Related: `AGENTS.md`, `docs/deployment/railway.md`,
`site/content/docs/build-apps/forms-data/`.

## Point Of View

You are the app author who wants small typed data helpers and the operator
reviewing migration artifacts before deployment.

## Protect

- **Data stays optional.** `pyproject.toml:56-57` keeps Postgres support behind
  `data-pg`; core rendering must not require database dependencies.
- **SQL parameters stay separate.** `pyproject.toml:175-176` documents why
  query/migration SQL generation has Ruff `S608` exceptions.
- **Rows prefer frozen dataclasses.** `src/chirp/data/_mapping.py` errors
  mention `@dataclass(frozen=True, slots=True)` for row mapping.
- **Migration output is deterministic.** Reviewable migrations matter more than
  clever generation.
- **Pagination/query behavior is public when documented.** Examples and docs
  make query helpers copyable.
- **Pools have concurrency boundaries.** Shared database state needs stress
  tests or explicit process/loop lifecycle reasoning.
- **Missing drivers are actionable.** Optional driver errors should name the
  extra to install.
- **Data is not app lifecycle.** Keep registration/freeze concerns in
  `src/chirp/app/`.

## Contract Checklist

When this domain changes, check:

- `src/chirp/data/database.py`, drivers, errors, `_mapping.py`, `_sqlite.py`.
- `src/chirp/data/query.py`, `pagination.py`, `migrate.py`,
  `schema/`, `types.py`.
- `src/chirp/app/__init__.py` db injection and
  `src/chirp/cli/_makemigrations.py`.
- README optional extras, data docs/examples, deployment notes, changelog.
- `tests/test_data.py`, `tests/test_query.py`, `tests/test_query_builder.py`.
- `tests/test_schema.py`, `tests/test_pagination.py`,
  `tests/test_concurrency/test_db_pool_stress.py`.

## Advocate

- **Migration previews.** Generated migrations should show reviewable SQL and
  caveats before execution.
- **Parameterized examples.** Docs should teach safe parameter binding by
  default.
- **Deterministic schema diffs.** Diff ordering should be stable across runs.
- **Driver absence tests.** Optional dependency errors should be covered.

## Do Not

- Become an ORM, admin system, or migration service.
- Make data dependencies mandatory for HTML-only apps.
- Build SQL by unsafe string concatenation.
- Hide generated migration risk behind convenience commands.

## Own

**Code:** `src/chirp/data/`.
**Tests:** data, query, schema, pagination, migration, and DB concurrency tests.
**Docs:** data docs, database examples, migration notes, deployment docs.
**Agent artifacts:** this file.
**CODEOWNERS:** manual-confirmation-needed; no CODEOWNERS file exists.
