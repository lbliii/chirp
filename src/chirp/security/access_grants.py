"""Per-record access grants — set-based authorization for lists and named policies.

Chirp's flat ``user.permissions`` gate answers route-level questions; this module
adds resource-level grants stored in an ``access_grants`` table and wired through
the existing named-policy seam (:func:`access_policy`) and
:meth:`~chirp.data.Query.accessible_to`.

Usage::

    from chirp.data import Database, Query, migrate
    from chirp.security.access_grants import (
        ACCESS_GRANTS_DDL,
        access_policy,
        check_access,
        create_grant,
        register_access_policy,
        require_access,
    )

    # One-time migration (copy ACCESS_GRANTS_DDL into migrations/NNN_access_grants.sql)
    await migrate(db, "migrations/")

    app.register_permission("documents.grant.read")
    register_access_policy(app, "owns:document", "document", param="document_id", perm="read")

    # List — one query, no N+1
    docs = await (
        Query(Doc, "documents")
        .accessible_to(user, "read", resource_type="document")
        .fetch(db)
    )

    # Detail route — AuthSpec(policy="owns:document") or imperative guard
    if not await check_access(db, user, "document", doc_id, "write"):
        ...
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal

from chirp.errors import HTTPError
from chirp.security.audit import emit_security_event
from chirp.security.auth_core import PolicyCallable

if TYPE_CHECKING:
    from chirp.data.database import Database

_log = logging.getLogger("chirp.security")

_SQL_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _sql_ident(name: str, *, label: str) -> str:
    if _SQL_IDENT.match(name) is None:
        msg = f"{label} must be a SQL identifier, got {name!r}"
        raise ValueError(msg)
    return name


GRANTS_TABLE = "access_grants"
PRINCIPAL_USER = "user"
PRINCIPAL_GROUP = "group"
PUBLIC_PRINCIPAL_ID = "*"
PERM_READ = "read"
PERM_WRITE = "write"
GrantPermission = Literal["read", "write"]
PrincipalType = Literal["user", "group"]

ACCESS_GRANTS_DDL = f"""
CREATE TABLE IF NOT EXISTS {GRANTS_TABLE} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    resource_type TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    principal_type TEXT NOT NULL CHECK (principal_type IN ('user', 'group')),
    principal_id TEXT NOT NULL,
    permission TEXT NOT NULL CHECK (permission IN ('read', 'write')),
    granted_by_user_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (resource_type, resource_id, principal_type, principal_id, permission)
);
CREATE INDEX IF NOT EXISTS idx_access_grants_grantee_user
    ON {GRANTS_TABLE} (resource_type, permission, principal_type, principal_id);
CREATE INDEX IF NOT EXISTS idx_access_grants_resource
    ON {GRANTS_TABLE} (resource_type, resource_id);
"""


@dataclass(frozen=True, slots=True)
class AccessGrant:
    """One row from ``access_grants``."""

    id: int
    resource_type: str
    resource_id: str
    principal_type: str
    principal_id: str
    permission: str
    granted_by_user_id: str
    created_at: str


class SharingEscalationError(Exception):
    """Raised when a user attempts to grant access beyond their feature permissions."""

    def __init__(self, errors: dict[str, list[str]]) -> None:
        self.errors = errors
        super().__init__(errors)


def _user_id(user: Any) -> str:
    return str(getattr(user, "id", ""))


def _user_group_ids(user: Any) -> frozenset[str]:
    raw = getattr(user, "group_ids", None)
    if raw is None:
        return frozenset()
    return frozenset(str(g) for g in raw)


def sharing_escalation_errors(
    user: Any,
    permission: str,
    *,
    resource_type: str,
) -> dict[str, list[str]]:
    """Return form field errors when *user* may not grant *permission* on *resource_type*.

    A user may grant ``read`` when they hold ``grant.read`` or
    ``{resource_type}.grant.read``; ``write`` requires the corresponding
    ``grant.write`` / ``{resource_type}.grant.write`` entries in
    ``user.permissions``. Fail loud — never silently narrow the grant.
    """
    held = getattr(user, "permissions", frozenset())
    if not isinstance(held, frozenset):
        held = frozenset(held)
    scoped = f"{resource_type}.grant.{permission}"
    global_key = f"grant.{permission}"
    if scoped in held or global_key in held:
        return {}
    return {
        "permission": [f"You cannot grant {permission!r} access for {resource_type!r} resources"]
    }


def access_exists_clause(
    *,
    table: str,
    resource_column: str,
    resource_type: str,
    perm: str,
    user_id: str,
    group_ids: tuple[str, ...],
    grants_table: str = GRANTS_TABLE,
) -> tuple[str, tuple[object, ...]]:
    """Build a correlated ``EXISTS`` WHERE fragment for set-based grant filtering."""
    table = _sql_ident(table, label="table")
    resource_column = _sql_ident(resource_column, label="resource_column")
    grants_table = _sql_ident(grants_table, label="grants_table")
    group_branch = ""
    params: list[object] = [resource_type, perm, user_id]
    if group_ids:
        placeholders = ", ".join("?" for _ in group_ids)
        group_branch = (
            f" OR (ag.principal_type = '{PRINCIPAL_GROUP}' AND ag.principal_id IN ({placeholders}))"
        )
        params.extend(group_ids)
    clause = (
        f"EXISTS (SELECT 1 FROM {grants_table} ag "
        f"WHERE ag.resource_type = ? "
        f"AND ag.resource_id = CAST({table}.{resource_column} AS TEXT) "
        f"AND ag.permission = ? "
        f"AND ((ag.principal_type = '{PRINCIPAL_USER}' AND ag.principal_id = ?) "
        f"OR (ag.principal_type = '{PRINCIPAL_USER}' AND ag.principal_id = '{PUBLIC_PRINCIPAL_ID}')"
        f"{group_branch}))"
    )
    return clause, tuple(params)


async def check_access(
    db: Database,
    user: Any,
    resource_type: str,
    resource_id: str,
    perm: str,
    *,
    group_ids: frozenset[str] | None = None,
    grants_table: str = GRANTS_TABLE,
) -> bool:
    """Return whether *user* holds *perm* on the given resource via grants."""
    if not getattr(user, "is_authenticated", False):
        return False
    grants_table = _sql_ident(grants_table, label="grants_table")
    groups = group_ids if group_ids is not None else _user_group_ids(user)
    group_clause = ""
    params: list[object] = [resource_type, str(resource_id), perm, _user_id(user)]
    if groups:
        placeholders = ", ".join("?" for _ in groups)
        group_clause = (
            f" OR (principal_type = '{PRINCIPAL_GROUP}' AND principal_id IN ({placeholders}))"
        )
        params.extend(sorted(groups))
    sql = (
        f"SELECT 1 FROM {grants_table} WHERE resource_type = ? AND resource_id = ? "
        f"AND permission = ? AND ("
        f"(principal_type = '{PRINCIPAL_USER}' AND principal_id = ?) "
        f"OR (principal_type = '{PRINCIPAL_USER}' AND principal_id = '{PUBLIC_PRINCIPAL_ID}')"
        f"{group_clause}) LIMIT 1"
    )
    row = await db.fetch_val(sql, *params)
    return row is not None


async def require_access(
    db: Database,
    user: Any,
    resource_type: str,
    resource_id: str,
    perm: str,
    *,
    request: Any | None = None,
    group_ids: frozenset[str] | None = None,
) -> None:
    """Raise ``HTTPError(403)`` and emit a security event when access is denied."""
    if await check_access(
        db,
        user,
        resource_type,
        resource_id,
        perm,
        group_ids=group_ids,
    ):
        return
    emit_security_event(
        "authz.access.denied",
        request=request,
        user_id=_user_id(user),
        details={
            "resource_type": resource_type,
            "resource_id": str(resource_id),
            "permission": perm,
        },
    )
    raise HTTPError(status=403, detail="Forbidden")


async def create_grant(
    db: Database,
    *,
    granter: Any,
    resource_type: str,
    resource_id: str,
    principal_type: PrincipalType,
    principal_id: str,
    permission: GrantPermission,
) -> AccessGrant:
    """Insert a grant after validating sharing escalation bounds.

    Raises :class:`SharingEscalationError` when *granter* lacks the feature
    permission to create a grant at *permission* level (fail loud, not silent strip).
    """
    errors = sharing_escalation_errors(granter, permission, resource_type=resource_type)
    if errors:
        raise SharingEscalationError(errors)
    created_at = datetime.now(tz=UTC).isoformat()
    await db.execute(
        f"INSERT INTO {GRANTS_TABLE} "
        "(resource_type, resource_id, principal_type, principal_id, permission, "
        "granted_by_user_id, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        resource_type,
        str(resource_id),
        principal_type,
        principal_id,
        permission,
        _user_id(granter),
        created_at,
    )
    row = await db.fetch_one(
        AccessGrant,
        f"SELECT * FROM {GRANTS_TABLE} WHERE rowid = last_insert_rowid()",
    )
    if row is None:
        msg = "grant insert succeeded but row could not be read back"
        raise RuntimeError(msg)
    return row


def access_policy(
    resource_type: str,
    *,
    param: str,
    perm: str = PERM_READ,
    owner_param: str | None = None,
    grants_table: str = GRANTS_TABLE,
) -> PolicyCallable:
    """Build a named-policy callable for ``AuthSpec(policy=...)`` / ``@requires``.

    Reads ``request.path_params[param]`` as the resource id and checks grants.
    When *owner_param* is set, a matching path param equal to ``user.id`` allows
    access without a grant row (explicit owner bypass at the call site).
    """
    from chirp.data.database import get_db

    async def _policy(user: Any, request: Any) -> bool:
        if owner_param is not None:
            owner_id = request.path_params.get(owner_param)
            if owner_id is not None and str(owner_id) == _user_id(user):
                return True
        resource_id = request.path_params.get(param)
        if resource_id is None:
            return False
        try:
            db = get_db()
        except LookupError:
            _log.warning(
                "access_policy(%r) could not resolve database — deny",
                resource_type,
            )
            return False
        return await check_access(
            db,
            user,
            resource_type,
            str(resource_id),
            perm,
            grants_table=grants_table,
        )

    _policy.__name__ = f"access_policy_{resource_type}_{perm}"
    return _policy


def register_access_policy(
    app: Any,
    name: str,
    resource_type: str,
    *,
    param: str,
    perm: str = PERM_READ,
    owner_param: str | None = None,
) -> None:
    """Register ``access_policy(...)`` under *name* via ``app.register_policy``."""
    app.register_policy(
        name,
        access_policy(
            resource_type,
            param=param,
            perm=perm,
            owner_param=owner_param,
        ),
    )


__all__ = [
    "ACCESS_GRANTS_DDL",
    "GRANTS_TABLE",
    "PERM_READ",
    "PERM_WRITE",
    "PRINCIPAL_GROUP",
    "PRINCIPAL_USER",
    "PUBLIC_PRINCIPAL_ID",
    "AccessGrant",
    "SharingEscalationError",
    "access_exists_clause",
    "access_policy",
    "check_access",
    "create_grant",
    "register_access_policy",
    "require_access",
    "sharing_escalation_errors",
]
