"""Typed-SQL column-mapping shape contract (#159).

``db.fetch(cls, sql)`` SELECTs a column that maps to no field on the frozen
dataclass (and is unknown to the declared schema) -> ERROR at ``app.check()``
time, instead of silently dropping the value at runtime.
"""

import ast
from dataclasses import dataclass

import pytest

from chirp.contracts.rules_data_shapes import (
    _parse_select_columns,
    check_data_shapes,
)
from chirp.contracts.types import Severity
from chirp.data.schema.parse import parse_schema


@dataclass(frozen=True, slots=True)
class User:
    id: int
    name: str
    email: str


# Module-level so handler ``__globals__`` can resolve the ``cls`` name.
SCHEMA = parse_schema("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, email TEXT);")


class _FakeRoute:
    def __init__(self, handler, path="/"):
        self.handler = handler
        self.path = path
        self.page_source_handler = None


class _FakeRouter:
    def __init__(self, *handlers):
        self.routes = [_FakeRoute(h, path=f"/r{i}") for i, h in enumerate(handlers)]


class TestParseSelectColumns:
    def test_simple_list(self) -> None:
        assert _parse_select_columns("SELECT id, name FROM users") == ("id", "name")

    def test_star_is_skipped(self) -> None:
        assert _parse_select_columns("SELECT * FROM users") is None

    def test_qualified_star_is_skipped(self) -> None:
        assert _parse_select_columns("SELECT users.* FROM users") is None

    def test_table_qualifier_stripped(self) -> None:
        assert _parse_select_columns("SELECT u.id, u.name FROM users u") == ("id", "name")

    def test_alias_uses_output_name(self) -> None:
        cols = _parse_select_columns("SELECT id, name AS full_name FROM users")
        assert cols == ("id", "full_name")

    def test_expression_is_skipped(self) -> None:
        assert _parse_select_columns("SELECT COUNT(*) AS n, id FROM users") == ("n", "id")
        # A bare expression with no alias is not analyzable.
        assert _parse_select_columns("SELECT id + 1 FROM users") is None

    def test_distinct_is_skipped(self) -> None:
        assert _parse_select_columns("SELECT DISTINCT id FROM users") is None

    def test_no_from_is_skipped(self) -> None:
        assert _parse_select_columns("PRAGMA table_info(users)") is None

    def test_cte_is_skipped(self) -> None:
        # The first SELECT/FROM lives inside the CTE body, not the output
        # projection, so the query is skipped rather than mis-analyzed.
        sql = "WITH t AS (SELECT id FROM users) SELECT id, bogus FROM t"
        assert _parse_select_columns(sql) is None

    def test_union_is_skipped(self) -> None:
        sql = "SELECT id FROM users UNION SELECT id FROM admins"
        assert _parse_select_columns(sql) is None

    def test_where_subquery_still_analyzed(self) -> None:
        # A subquery in WHERE does not move the output projection, so the outer
        # SELECT list is still analyzable (the first SELECT/FROM is the outer).
        sql = "SELECT id, name FROM users WHERE id IN (SELECT user_id FROM admins)"
        assert _parse_select_columns(sql) == ("id", "name")


class TestCheckDataShapes:
    def test_drifted_column_errors(self) -> None:
        def handler():
            db = object()
            return db.fetch(User, "SELECT id, naem FROM users")  # typo: naem

        issues = check_data_shapes(_FakeRouter(handler), SCHEMA)
        assert len(issues) == 1
        issue = issues[0]
        assert issue.severity == Severity.ERROR
        assert issue.category == "data"
        assert "naem" in issue.message
        assert "User" in issue.message
        assert issue.route == "/r0"

    def test_matching_columns_clean(self) -> None:
        def handler():
            db = object()
            return db.fetch(User, "SELECT id, name, email FROM users")

        assert check_data_shapes(_FakeRouter(handler), SCHEMA) == []

    def test_non_db_receiver_not_flagged(self) -> None:
        # ``fetch``/``stream`` are generic method names. A call on an unrelated
        # object (an LLM client, a query builder) must NOT emit a build-breaking
        # ERROR even with a dataclass + string-literal SQL-looking first args.
        def handler():
            llm = object()
            client = object()
            llm.stream(User, "SELECT id, naem FROM users")  # not a db handle
            return client.fetch(User, "SELECT id, ghost FROM users")

        assert check_data_shapes(_FakeRouter(handler), SCHEMA) == []

    def test_db_attribute_and_get_db_receivers_checked(self) -> None:
        # The canonical db accessors are still analyzed: ``self.db``, ``app.db``,
        # a ``*_db`` name, and ``get_db()``.
        def handler_self():
            self = object()
            return self.db.fetch(User, "SELECT id, naem FROM users")

        def handler_app():
            app = object()
            return app.db.fetch(User, "SELECT id, naem FROM users")

        def handler_suffix():
            user_db = object()
            return user_db.fetch(User, "SELECT id, naem FROM users")

        def handler_get_db():
            return get_db().fetch(User, "SELECT id, naem FROM users")  # noqa: F821

        for h in (handler_self, handler_app, handler_suffix, handler_get_db):
            issues = check_data_shapes(_FakeRouter(h), SCHEMA)
            assert len(issues) == 1, f"{h.__name__}: expected 1 issue, got {issues}"
            assert "naem" in issues[0].message

    def test_fetch_one_checked(self) -> None:
        def handler():
            db = object()
            return db.fetch_one(User, "SELECT id, bogus FROM users WHERE id = ?", 1)

        issues = check_data_shapes(_FakeRouter(handler), SCHEMA)
        assert len(issues) == 1
        assert "bogus" in issues[0].message

    def test_stream_checked(self) -> None:
        def handler():
            db = object()
            return db.stream(User, "SELECT id, missing FROM users")

        issues = check_data_shapes(_FakeRouter(handler), SCHEMA)
        assert len(issues) == 1
        assert "missing" in issues[0].message

    def test_select_star_skipped(self) -> None:
        def handler():
            db = object()
            return db.fetch(User, "SELECT * FROM users")

        assert check_data_shapes(_FakeRouter(handler), SCHEMA) == []

    def test_dynamic_sql_skipped(self) -> None:
        def handler():
            db = object()
            col = "naem"
            return db.fetch(User, f"SELECT id, {col} FROM users")  # noqa: S608

        assert check_data_shapes(_FakeRouter(handler), SCHEMA) == []

    def test_computed_cls_skipped(self) -> None:
        def handler():
            db = object()
            cls = User
            return db.fetch(cls, "SELECT id, naem FROM users")

        # ``cls`` is a local name, not resolvable in module globals -> skip.
        assert check_data_shapes(_FakeRouter(handler), SCHEMA) == []

    def test_non_dataclass_cls_skipped(self) -> None:
        def handler():
            db = object()
            return db.fetch(dict, "SELECT id, naem FROM users")

        assert check_data_shapes(_FakeRouter(handler), SCHEMA) == []

    def test_subset_of_fields_is_clean(self) -> None:
        # SELECTing only some of the dataclass fields is fine: missing-from-row
        # would raise at runtime, but extra-on-dataclass is not this rule's job.
        def handler():
            db = object()
            return db.fetch(User, "SELECT id, name FROM users")

        assert check_data_shapes(_FakeRouter(handler), SCHEMA) == []

    def test_no_schema_flags_unknown_column(self) -> None:
        # Without a declared schema, a column matching no field is still drift.
        def handler():
            db = object()
            return db.fetch(User, "SELECT id, ghost FROM users")

        issues = check_data_shapes(_FakeRouter(handler), None)
        assert len(issues) == 1
        assert "ghost" in issues[0].message
        assert "no declared" in (issues[0].details or "")

    def test_unknown_column_in_schema_not_flagged_when_field_absent(self) -> None:
        # A column present in SOME declared table but absent from the dataclass
        # fields is a legitimate non-read, not a typo -> stay quiet.
        schema = parse_schema(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, email TEXT);"
            "CREATE TABLE audits (id INTEGER PRIMARY KEY, note TEXT);"
        )

        def handler():
            db = object()
            # `note` is a real column in `audits`, just not a User field.
            return db.fetch(User, "SELECT id, note FROM users JOIN audits")

        # JOIN query -> projection is still simple identifiers, but `note` is a
        # known schema column, so no drift is reported.
        assert check_data_shapes(_FakeRouter(handler), schema) == []

    def test_dedupes_same_offender(self) -> None:
        def handler():
            db = object()
            db.fetch(User, "SELECT naem FROM users")
            return db.fetch(User, "SELECT naem FROM users WHERE id = ?", 1)

        issues = check_data_shapes(_FakeRouter(handler), SCHEMA)
        assert len(issues) == 1

    def test_no_router_routes_noop(self) -> None:
        assert check_data_shapes(object(), SCHEMA) == []


class TestDataShapesAst:
    """Sanity-check the AST extraction helper directly."""

    def test_iter_fetch_calls_finds_literal(self) -> None:
        from chirp.contracts.rules_data_shapes import _iter_fetch_calls

        tree = ast.parse('db.fetch(User, "SELECT id FROM users")')
        calls = _iter_fetch_calls(tree)
        assert len(calls) == 1
        cls_node, sql = calls[0]
        assert isinstance(cls_node, ast.Name)
        assert sql == "SELECT id FROM users"

    def test_iter_fetch_calls_skips_non_literal_sql(self) -> None:
        from chirp.contracts.rules_data_shapes import _iter_fetch_calls

        tree = ast.parse("db.fetch(User, build_sql())")
        assert _iter_fetch_calls(tree) == []


class TestDataShapesIntegration:
    """The rule must run inside ``app.check()`` and stay a no-op without a db."""

    @pytest.mark.asyncio
    async def test_app_check_noop_without_migrations(self, tmp_path) -> None:
        from chirp import App
        from chirp.config import AppConfig
        from chirp.contracts import check_hypermedia_surface

        template_dir = tmp_path / "templates"
        template_dir.mkdir()
        (template_dir / "page.html").write_text("<html><body>hi</body></html>")
        app = App(config=AppConfig(template_dir=str(template_dir)))

        @app.route("/")
        def index():
            from chirp.templating.returns import Template

            return Template("page.html")

        app._freeze()
        result = check_hypermedia_surface(app)
        assert [i for i in result.issues if i.category == "data"] == []
        # Snapshot schema must be None for a db-less app.
        snapshot = app._contract_check_snapshot()
        assert snapshot.schema is None

    @pytest.mark.asyncio
    async def test_app_check_flags_drift_with_migrations(self, tmp_path) -> None:
        from chirp import App
        from chirp.config import AppConfig
        from chirp.contracts import check_hypermedia_surface

        template_dir = tmp_path / "templates"
        template_dir.mkdir()
        (template_dir / "page.html").write_text("<html><body>hi</body></html>")
        migrations = tmp_path / "migrations"
        migrations.mkdir()
        (migrations / "001_users.sql").write_text(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, email TEXT);"
        )
        app = App(
            db="sqlite:///:memory:",
            migrations=str(migrations),
            config=AppConfig(template_dir=str(template_dir)),
        )

        @app.route("/users")
        async def users():
            from chirp.data import get_db
            from chirp.templating.returns import Template

            db = get_db()
            await db.fetch(User, "SELECT id, naem FROM users")
            return Template("page.html")

        app._freeze()
        snapshot = app._contract_check_snapshot()
        assert snapshot.schema is not None
        assert "users" in snapshot.schema.tables

        result = check_hypermedia_surface(app)
        data_issues = [i for i in result.issues if i.category == "data"]
        assert len(data_issues) == 1
        assert data_issues[0].severity == Severity.ERROR
        assert "naem" in data_issues[0].message

    @pytest.mark.asyncio
    async def test_severity_override(self, tmp_path) -> None:
        from chirp import App
        from chirp.config import AppConfig
        from chirp.contracts import check_hypermedia_surface

        template_dir = tmp_path / "templates"
        template_dir.mkdir()
        (template_dir / "page.html").write_text("<html><body>hi</body></html>")
        migrations = tmp_path / "migrations"
        migrations.mkdir()
        (migrations / "001_users.sql").write_text(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, email TEXT);"
        )
        app = App(
            db="sqlite:///:memory:",
            migrations=str(migrations),
            config=AppConfig(template_dir=str(template_dir)),
        )
        app.override_contract_severity("data", Severity.WARNING)

        @app.route("/users")
        async def users():
            from chirp.data import get_db
            from chirp.templating.returns import Template

            db = get_db()
            await db.fetch(User, "SELECT id, naem FROM users")
            return Template("page.html")

        app._freeze()
        result = check_hypermedia_surface(app)
        data_issues = [i for i in result.issues if i.category == "data"]
        assert len(data_issues) == 1
        assert data_issues[0].severity == Severity.WARNING
