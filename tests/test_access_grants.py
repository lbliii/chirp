"""Tests for per-record access grants (#371, #376, #872)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import pytest

from chirp import App
from chirp.data import Database, Query
from chirp.data.database import _db_var
from chirp.data.errors import QueryError
from chirp.errors import HTTPError
from chirp.pages.types import AuthSpec
from chirp.security.access_grants import (
    ACCESS_GRANTS_DDL,
    SharingEscalationError,
    access_grants_ddl,
    access_policy,
    check_access,
    create_grant,
    register_access_policy,
    require_access,
    sharing_escalation_errors,
)
from chirp.security.audit import SecurityEvent, set_security_event_sink
from chirp.security.auth_core import enforce_auth
from chirp.templating.returns import ValidationError

# Live PostgreSQL coverage mirrors tests/test_schema_introspect.py — gated on
# CHIRP_TEST_PG_DSN so local SQLite-only runs and the free-threaded main job stay green.
PG_DSN = os.environ.get("CHIRP_TEST_PG_DSN")
requires_pg = pytest.mark.skipif(
    not PG_DSN,
    reason="CHIRP_TEST_PG_DSN not set — PostgreSQL access-grant coverage skipped",
)


@dataclass(frozen=True, slots=True)
class Doc:
    id: int
    title: str
    owner_id: str


@dataclass(frozen=True, slots=True)
class GrantUser:
    id: str
    is_authenticated: bool = True
    permissions: frozenset[str] = frozenset()
    group_ids: frozenset[str] = frozenset()


async def _seed_documents(db: Database) -> None:
    await db.execute("CREATE TABLE documents (id INTEGER PRIMARY KEY, title TEXT, owner_id TEXT)")
    await db.execute("INSERT INTO documents (id, title, owner_id) VALUES (1, 'a', 'alice')")
    await db.execute("INSERT INTO documents (id, title, owner_id) VALUES (2, 'b', 'bob')")
    await db.execute("INSERT INTO documents (id, title, owner_id) VALUES (3, 'c', 'carol')")


@pytest.fixture
async def grants_db(tmp_path):
    db = Database(f"sqlite:///{tmp_path / 'grants.db'}")
    await db.connect()
    await db.execute_script(access_grants_ddl("sqlite"))
    await _seed_documents(db)
    yield db
    await db.disconnect()


@pytest.fixture
def security_events():
    events: list[SecurityEvent] = []

    def _sink(event: SecurityEvent) -> None:
        events.append(event)

    set_security_event_sink(_sink)
    yield events
    set_security_event_sink(None)


@pytest.mark.issue(872)
class TestAccessGrantsDdlPortability:
    def test_sqlite_ddl_omits_autoincrement_and_matches_constant(self) -> None:
        ddl = access_grants_ddl("sqlite")
        assert ddl == ACCESS_GRANTS_DDL
        assert "AUTOINCREMENT" not in ddl
        assert "id INTEGER PRIMARY KEY" in ddl
        assert "SERIAL" not in ddl

    def test_postgresql_ddl_uses_serial(self) -> None:
        ddl = access_grants_ddl("postgresql")
        assert "id SERIAL PRIMARY KEY" in ddl
        assert "AUTOINCREMENT" not in ddl
        assert access_grants_ddl("postgres") == ddl

    def test_unknown_dialect_fails_loud(self) -> None:
        with pytest.raises(ValueError, match="unsupported access-grants dialect"):
            access_grants_ddl("mysql")


@pytest.mark.issue(371)
class TestCheckAccess:
    async def test_direct_user_grant(self, grants_db: Database) -> None:
        await grants_db.execute(
            "INSERT INTO access_grants "
            "(resource_type, resource_id, principal_type, principal_id, permission, "
            "granted_by_user_id, created_at) "
            "VALUES ('document', '1', 'user', 'alice', 'read', 'admin', 't')",
        )
        user = GrantUser(id="alice")
        assert await check_access(grants_db, user, "document", "1", "read")

    async def test_public_grant(self, grants_db: Database) -> None:
        await grants_db.execute(
            "INSERT INTO access_grants "
            "(resource_type, resource_id, principal_type, principal_id, permission, "
            "granted_by_user_id, created_at) "
            "VALUES ('document', '2', 'user', '*', 'read', 'admin', 't')",
        )
        user = GrantUser(id="stranger")
        assert await check_access(grants_db, user, "document", "2", "read")

    async def test_group_grant(self, grants_db: Database) -> None:
        await grants_db.execute(
            "INSERT INTO access_grants "
            "(resource_type, resource_id, principal_type, principal_id, permission, "
            "granted_by_user_id, created_at) "
            "VALUES ('document', '3', 'group', 'editors', 'read', 'admin', 't')",
        )
        user = GrantUser(id="bob", group_ids=frozenset({"editors"}))
        assert await check_access(grants_db, user, "document", "3", "read")

    async def test_deny_without_grant(self, grants_db: Database) -> None:
        user = GrantUser(id="alice")
        assert not await check_access(grants_db, user, "document", "1", "read")

    async def test_require_access_emits_security_event(
        self,
        grants_db: Database,
        security_events: list[SecurityEvent],
    ) -> None:
        user = GrantUser(id="alice")
        with pytest.raises(HTTPError) as exc:
            await require_access(grants_db, user, "document", "1", "read")
        assert exc.value.status == 403
        denied = [e for e in security_events if e.name == "authz.access.denied"]
        assert len(denied) == 1
        assert denied[0].details == {
            "resource_type": "document",
            "resource_id": "1",
            "permission": "read",
        }


@pytest.mark.issue(371)
class TestAccessibleTo:
    async def test_filters_list_in_one_query(self, grants_db: Database) -> None:
        await grants_db.execute(
            "INSERT INTO access_grants "
            "(resource_type, resource_id, principal_type, principal_id, permission, "
            "granted_by_user_id, created_at) "
            "VALUES ('document', '1', 'user', 'alice', 'read', 'admin', 't')",
        )
        await grants_db.execute(
            "INSERT INTO access_grants "
            "(resource_type, resource_id, principal_type, principal_id, permission, "
            "granted_by_user_id, created_at) "
            "VALUES ('document', '2', 'user', 'alice', 'read', 'admin', 't')",
        )
        user = GrantUser(id="alice")
        rows = await (
            Query(Doc, "documents")
            .accessible_to(user, "read", resource_type="document")
            .order_by("id")
            .fetch(grants_db)
        )
        assert [r.id for r in rows] == [1, 2]

    def test_compiles_exists_subquery(self) -> None:
        user = GrantUser(id="alice", group_ids=frozenset({"g1"}))
        q = Query(Doc, "documents").accessible_to(user, "read", resource_type="document")
        assert "EXISTS" in q.sql
        assert "access_grants" in q.sql
        assert q.params[0] == "document"
        assert q.params[1] == "read"
        assert q.params[2] == "alice"
        assert "g1" in q.params


@pytest.mark.issue(371)
class TestAccessPolicy:
    async def test_named_policy_allows_with_grant(self, grants_db: Database) -> None:
        await grants_db.execute(
            "INSERT INTO access_grants "
            "(resource_type, resource_id, principal_type, principal_id, permission, "
            "granted_by_user_id, created_at) "
            "VALUES ('document', '42', 'user', 'alice', 'read', 'admin', 't')",
        )
        token = _db_var.set(grants_db)
        try:
            policy = access_policy("document", param="document_id", perm="read")

            @dataclass
            class _Req:
                path_params: dict[str, str]

            allowed = await policy(GrantUser(id="alice"), _Req(path_params={"document_id": "42"}))
            assert allowed
        finally:
            _db_var.reset(token)

    async def test_named_policy_denies_without_grant(self, grants_db: Database) -> None:
        token = _db_var.set(grants_db)
        try:
            policy = access_policy("document", param="document_id", perm="read")

            @dataclass
            class _Req:
                path_params: dict[str, str]

            allowed = await policy(GrantUser(id="alice"), _Req(path_params={"document_id": "99"}))
            assert not allowed
        finally:
            _db_var.reset(token)

    async def test_owner_bypass(self, grants_db: Database) -> None:
        token = _db_var.set(grants_db)
        try:
            policy = access_policy(
                "document",
                param="document_id",
                perm="read",
                owner_param="owner_id",
            )

            @dataclass
            class _Req:
                path_params: dict[str, str]

            allowed = await policy(
                GrantUser(id="alice"),
                _Req(path_params={"document_id": "99", "owner_id": "alice"}),
            )
            assert allowed
        finally:
            _db_var.reset(token)

    async def test_auth_spec_policy_gate_403(
        self,
        grants_db: Database,
        security_events: list[SecurityEvent],
    ) -> None:
        token = _db_var.set(grants_db)
        try:
            spec = AuthSpec(policy="owns:document")
            policy = access_policy("document", param="document_id")

            def resolver(name: str):
                return policy if name == "owns:document" else None

            @dataclass
            class _Req:
                path_params: dict[str, str] = field(default_factory=lambda: {"document_id": "1"})

            with pytest.raises(HTTPError) as exc:
                await enforce_auth(spec, _Req(), GrantUser(id="alice"), policy_resolver=resolver)
            assert exc.value.status == 403
            assert any(e.name == "authz.policy.denied" for e in security_events)
        finally:
            _db_var.reset(token)

    async def test_register_access_policy_on_app(self, grants_db: Database) -> None:
        app = App(db=grants_db)
        register_access_policy(app, "owns:document", "document", param="document_id")
        assert "owns:document" in app._mutable_state.policy_registry


@pytest.mark.issue(376)
class TestSharingEscalation:
    def test_escalation_errors_when_missing_grant_permission(self) -> None:
        user = GrantUser(id="alice", permissions=frozenset({"document.grant.read"}))
        errors = sharing_escalation_errors(user, "write", resource_type="document")
        assert "permission" in errors

    def test_no_errors_when_permission_held(self) -> None:
        user = GrantUser(id="alice", permissions=frozenset({"grant.write"}))
        assert sharing_escalation_errors(user, "write", resource_type="document") == {}

    async def test_create_grant_raises_on_escalation(self, grants_db: Database) -> None:
        granter = GrantUser(id="alice", permissions=frozenset({"document.grant.read"}))
        with pytest.raises(SharingEscalationError) as exc:
            await create_grant(
                grants_db,
                granter=granter,
                resource_type="document",
                resource_id="1",
                principal_type="user",
                principal_id="bob",
                permission="write",
            )
        assert "permission" in exc.value.errors

    async def test_create_grant_inserts_when_allowed(self, grants_db: Database) -> None:
        granter = GrantUser(id="alice", permissions=frozenset({"document.grant.write"}))
        grant = await create_grant(
            grants_db,
            granter=granter,
            resource_type="document",
            resource_id="1",
            principal_type="user",
            principal_id="bob",
            permission="write",
        )
        assert isinstance(grant.id, int)
        assert grant.resource_id == "1"
        assert grant.permission == "write"
        bob = GrantUser(id="bob")
        assert await check_access(grants_db, bob, "document", "1", "write")

    @pytest.mark.issue(872)
    async def test_create_grant_duplicate_fails_loud(self, grants_db: Database) -> None:
        granter = GrantUser(id="alice", permissions=frozenset({"document.grant.read"}))
        await create_grant(
            grants_db,
            granter=granter,
            resource_type="document",
            resource_id="1",
            principal_type="user",
            principal_id="bob",
            permission="read",
        )
        with pytest.raises(QueryError):
            await create_grant(
                grants_db,
                granter=granter,
                resource_type="document",
                resource_id="1",
                principal_type="user",
                principal_id="bob",
                permission="read",
            )
        # Duplicate failure must not leave a second row or wipe the first grant.
        bob = GrantUser(id="bob")
        assert await check_access(grants_db, bob, "document", "1", "read")

    async def test_validation_error_pattern_for_form_handler(self, grants_db: Database) -> None:
        granter = GrantUser(id="alice", permissions=frozenset())
        with pytest.raises(SharingEscalationError) as exc_info:
            await create_grant(
                grants_db,
                granter=granter,
                resource_type="document",
                resource_id="1",
                principal_type="user",
                principal_id="bob",
                permission="read",
            )
        err = ValidationError(
            "share.html",
            "grant_form",
            errors=exc_info.value.errors,
            form={"principal_id": "bob"},
        )
        assert err.context["errors"]["permission"]
        assert err.context["form"]["principal_id"] == "bob"


async def _drop_pg_grant_tables(db: Database) -> None:
    await db.execute("DROP TABLE IF EXISTS access_grants CASCADE")
    await db.execute("DROP TABLE IF EXISTS documents CASCADE")


@requires_pg
@pytest.mark.issue(872)
class TestAccessGrantsPostgres:
    """Live PostgreSQL parity for DDL apply, create_grant, and check_access."""

    async def test_create_grant_and_checks_on_postgresql(self) -> None:
        assert PG_DSN is not None
        db = Database(PG_DSN)
        await db.connect()
        try:
            assert db._driver == "postgresql"
            await _drop_pg_grant_tables(db)
            await db.execute_script(access_grants_ddl("postgresql"))
            await _seed_documents(db)

            granter = GrantUser(
                id="alice",
                permissions=frozenset({"document.grant.read", "document.grant.write"}),
            )
            read_grant = await create_grant(
                db,
                granter=granter,
                resource_type="document",
                resource_id="1",
                principal_type="user",
                principal_id="bob",
                permission="read",
            )
            assert isinstance(read_grant.id, int)
            assert read_grant.principal_id == "bob"

            write_grant = await create_grant(
                db,
                granter=granter,
                resource_type="document",
                resource_id="2",
                principal_type="user",
                principal_id="*",
                permission="write",
            )
            assert write_grant.permission == "write"

            await create_grant(
                db,
                granter=granter,
                resource_type="document",
                resource_id="3",
                principal_type="group",
                principal_id="editors",
                permission="read",
            )

            bob = GrantUser(id="bob")
            stranger = GrantUser(id="stranger")
            editor = GrantUser(id="carol", group_ids=frozenset({"editors"}))

            assert await check_access(db, bob, "document", "1", "read")
            assert not await check_access(db, bob, "document", "1", "write")
            assert await check_access(db, stranger, "document", "2", "write")
            assert await check_access(db, editor, "document", "3", "read")
            assert not await check_access(db, stranger, "document", "3", "read")

            rows = await (
                Query(Doc, "documents")
                .accessible_to(bob, "read", resource_type="document")
                .order_by("id")
                .fetch(db)
            )
            assert [r.id for r in rows] == [1]

            with pytest.raises(QueryError):
                await create_grant(
                    db,
                    granter=granter,
                    resource_type="document",
                    resource_id="1",
                    principal_type="user",
                    principal_id="bob",
                    permission="read",
                )
            assert await check_access(db, bob, "document", "1", "read")
        finally:
            try:
                await _drop_pg_grant_tables(db)
            finally:
                await db.disconnect()
