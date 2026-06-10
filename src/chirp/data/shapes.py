"""Verified SQL-to-render data shapes.

A *Shape* is a frozen, slotted dataclass that declares — co-located with the
row model — the ``SELECT`` that produces it. Decorate the row dataclass with
``@shape("SELECT ...")`` and the declared SQL becomes the single source of truth
for what columns the row carries::

    from dataclasses import dataclass
    from chirp.data import Database, Shape, shape

    @shape("SELECT id, title FROM boards WHERE id = :id")
    @dataclass(frozen=True, slots=True)
    class BoardView:
        id: int
        title: str

    boards = await Shape.fetch(BoardView, db, id=42)

The compiled SQL and all execution live **behind** the ``Database`` facade
(the ``Shape.fetch`` / ``Shape.fetch_one`` / ``Shape.stream`` classmethods,
which delegate to ``Database``) — never in template-adjacent code and never as
a SQL string threaded through a handler kwarg into a template. The author writes
``:name`` placeholders; the driver dialect (``?`` for SQLite, ``$N`` for
PostgreSQL) is resolved in one place (``_bind_params``) so parameters are never
concatenated into the SQL text.

Free-threading lifecycle:
    - The decorated class is the row type; ``@shape`` attaches a single frozen
      ``_ShapeMeta`` sidecar (``cls.__chirp_shape__``) once at decoration and
      never mutates it thereafter.
    - The module-level shape registry is shared mutable state. Both writes and
      reads are guarded by a ``threading.Lock``; ``shape_registry()`` returns a
      read-only ``MappingProxyType`` copy. Registration happens at decoration /
      import time; the registry is treated read-only after app setup.
"""

from __future__ import annotations

import dataclasses
import re
import threading
import types as _types
import typing
from collections.abc import AsyncIterator, Mapping, Sequence
from typing import TYPE_CHECKING, Any, TypeVar, get_args, get_origin

from chirp.contracts.rules_data_shapes import _parse_select_columns
from chirp.data.errors import ShapeError

if TYPE_CHECKING:
    from chirp.data.database import Database

T = TypeVar("T")

# Metadata key carrying a NestedShape on a dataclass field (see nested()).
_NESTED_META_KEY = "chirp_nested"


@dataclasses.dataclass(frozen=True, slots=True)
class NestedShape:
    """Explicit child-Shape declaration for the bounded compiler (#167).

    Created via :func:`nested` and recorded in the field's metadata. The child
    ``cls`` MUST itself be ``@shape``-decorated (it carries its own SQL). The
    compiler runs ONE batched ``IN``-list query per child *level* (never per
    parent row), groups children by the ``on`` column, and attaches them to each
    parent via :func:`dataclasses.replace`.

    Attributes:
        cls: The child row Shape (a ``@shape``-decorated frozen dataclass).
        field: The parent dataclass field the children attach to (a tuple).
        on: The child SQL column joining back to the parent key.
        key: The parent column whose values seed the child ``IN`` list.
        optional: When ``True`` the child level is skipped for parents whose
            ``key`` value is ``None`` (RFC-line-115 conditionally-assembled
            children expressible as a declared-optional child).
    """

    cls: type
    field: str
    on: str
    key: str
    optional: bool = False


@dataclasses.dataclass(frozen=True, slots=True)
class _ShapeMeta:
    """Immutable sidecar describing a ``@shape``-decorated dataclass.

    Attached to the class as ``cls.__chirp_shape__`` once at decoration and
    never mutated (frozen-clean for free-threaded 3.14t).
    """

    sql: str
    columns: tuple[str, ...]  # parsed output names of the SELECT (() == opaque)
    computed: frozenset[str]  # declared computed/derived members (#168)
    scope: str | None  # tenant scope key (#169)
    name: str  # registry name (defaults to cls.__name__)
    nested: tuple[NestedShape, ...] = ()  # NestedShape entries (#167)


def nested(
    child: type,
    *,
    on: str,
    key: str,
    optional: bool = False,
) -> Any:
    """Declare a nested child Shape on a parent ``@shape`` field (#167).

    Returns a :func:`dataclasses.field` with an empty-tuple default and the
    :class:`NestedShape` metadata, so the parent's row mapping (``map_row``'s
    ``cls(**filtered)``, which keeps only keys present in the SQL row) does not
    raise for the absent nested column. ``@shape`` collects these from
    :func:`dataclasses.fields` and the bounded compiler fills them in.

    Usage::

        @shape("SELECT id, title FROM boards WHERE id = :id")
        @dataclass(frozen=True, slots=True)
        class Board:
            id: int
            title: str
            cards: tuple[Card, ...] = nested(Card, on="board_id", key="id")

    The empty-tuple default forces a field-ordering constraint: every
    ``nested()`` field must come AFTER all scalar (no-default) fields.
    ``@shape`` fails loud (``ShapeError``) if a no-default scalar field follows
    a ``nested()`` field, rather than letting Python raise the opaque
    "non-default argument follows default argument".

    Args:
        child: The child row Shape (a ``@shape``-decorated frozen dataclass).
        on: The child SQL column joining back to the parent ``key``.
        key: The parent column seeding the child ``IN`` list.
        optional: Skip the child level for a parent whose ``key`` is ``None``.
    """
    return dataclasses.field(
        default=(),
        metadata={_NESTED_META_KEY: (child, on, key, optional)},
    )


def _collect_nested(cls: type) -> tuple[NestedShape, ...]:
    """Collect declared nested children from a dataclass's field metadata.

    Walks :func:`dataclasses.fields` for the ``chirp_nested`` metadata planted
    by :func:`nested` and fails loud (``ShapeError``) when a no-default scalar
    field follows a nested field (§8.2 #2) -- surfacing the field-ordering
    constraint clearly instead of relying on Python's opaque class-creation
    error (which is also pre-empted by the empty-tuple default ``nested`` sets).
    """
    entries: list[NestedShape] = []
    seen_nested = False
    for f in dataclasses.fields(cls):
        spec = f.metadata.get(_NESTED_META_KEY)
        if spec is not None:
            child, on, key, optional = spec
            entries.append(NestedShape(cls=child, field=f.name, on=on, key=key, optional=optional))
            seen_nested = True
            continue
        # A scalar (non-nested) field with no default following a nested field
        # violates dataclass ordering. Python already raised at class creation
        # for the no-default case; here we additionally fail loud for a scalar
        # field WITH a default declared after a nested field, which Python
        # accepts but breaks the "nested fields come last" invariant the
        # compiler relies on (parent rows map cleanly; children append last).
        if seen_nested:
            msg = (
                f"@shape: field {f.name!r} on {cls.__name__} is declared after a "
                "nested() field. All nested() child fields must come AFTER every "
                "scalar field. Move the scalar fields above the nested() fields."
            )
            raise ShapeError(msg)
    return tuple(entries)


# Module-global registry of named Shapes. Shared mutable state on free-threaded
# 3.14t — guard BOTH writes and the shape_registry() read with this lock, and
# return a read-only copy. Registration is decoration/import-time; the registry
# is treated read-only after app setup.
_SHAPE_REGISTRY: dict[str, type] = {}
_REGISTRY_LOCK = threading.Lock()


def register_shape(name: str, cls: type) -> None:
    """Register a named Shape in the module-level registry.

    Called automatically by ``@shape`` so every shape is discoverable for
    drift detection (#166/#172); may also be called explicitly to alias a name.

    Same-name collision policy (fail-loud, not last-wins-silently):

    * registering the **same** class under a name is idempotent (no-op);
    * registering a **different** class under an already-registered name raises
      :class:`ShapeError`.
    """
    with _REGISTRY_LOCK:
        existing = _SHAPE_REGISTRY.get(name)
        if existing is None:
            _SHAPE_REGISTRY[name] = cls
            return
        if existing is cls:
            return
        msg = (
            f"Shape name {name!r} is already registered to "
            f"{existing.__module__}.{existing.__qualname__}; "
            f"cannot re-register it to {cls.__module__}.{cls.__qualname__}. "
            "Give one of them a distinct name via @shape(..., name=...)."
        )
        raise ShapeError(msg)


def shape_registry() -> Mapping[str, type]:
    """Return a read-only snapshot of registered named Shapes.

    Consumed by the ``shapecheck`` contract (#166) for registry-drift
    detection. The returned mapping is an immutable copy taken under the
    registry lock — callers cannot mutate the live registry through it.
    """
    with _REGISTRY_LOCK:
        return _types.MappingProxyType(dict(_SHAPE_REGISTRY))


def _validate_target(cls: type) -> None:
    """Raise :class:`ShapeError` unless ``cls`` is a frozen, slotted dataclass."""
    if not dataclasses.is_dataclass(cls):
        msg = (
            f"@shape requires a dataclass, got {cls!r}. "
            "Decorate a @dataclass(frozen=True, slots=True) row model."
        )
        raise ShapeError(msg)
    params = getattr(cls, "__dataclass_params__", None)
    if params is None or not params.frozen:
        msg = (
            f"@shape requires a frozen dataclass, but {cls.__name__} is not frozen. "
            "Use @dataclass(frozen=True, slots=True)."
        )
        raise ShapeError(msg)
    if getattr(cls, "__slots__", None) is None:
        msg = (
            f"@shape requires a slotted dataclass, but {cls.__name__} has no __slots__. "
            "Use @dataclass(frozen=True, slots=True)."
        )
        raise ShapeError(msg)


def shape(
    sql: str,
    *,
    computed: Sequence[str] = (),
    scope: str | None = None,
    name: str | None = None,
) -> Any:
    """Declare a verified SQL row Shape on a frozen, slotted dataclass.

    The decorated dataclass *is* the row type (identity decorator). The declared
    ``sql`` is parsed for its output column list and stored — with the
    ``computed`` members and tenant ``scope`` key — in a frozen ``_ShapeMeta``
    sidecar on ``cls.__chirp_shape__``. The shape is auto-registered under
    ``name`` (defaults to ``cls.__name__``).

    Args:
        sql: The declared ``SELECT``. Author writes ``:name`` placeholders;
            the driver dialect is resolved at fetch time (never concatenated).
        computed: Declared computed/derived members not present as SELECT
            columns (widens the verified field set for ``shapecheck``).
        scope: Tenant scope key (honored by the L3 compiler; stored only in L1).
        name: Registry name; defaults to ``cls.__name__``.

    Raises:
        ShapeError: if the target is not a frozen, slotted dataclass.

    Opaque SQL (``SELECT *``, expression projections, CTE/UNION) yields
    ``columns=()`` — an explicit escape hatch that ``shapecheck`` treats as
    "skip, never false-positive."
    """

    def decorate(cls: type[T]) -> type[T]:
        _validate_target(cls)
        parsed = _parse_select_columns(sql)
        columns = parsed if parsed is not None else ()
        registry_name = name if name is not None else cls.__name__
        nested_children = _collect_nested(cls)
        meta = _ShapeMeta(
            sql=sql,
            columns=columns,
            computed=frozenset(computed),
            scope=scope,
            name=registry_name,
            nested=nested_children,
        )
        # Attach the frozen sidecar once at decoration (immutable thereafter).
        # setattr keeps the dynamic attribute out of the class's declared
        # surface without a type-ignore suppression.
        setattr(cls, "__chirp_shape__", meta)  # noqa: B010 — dynamic sentinel attr
        register_shape(registry_name, cls)
        return cls

    return decorate


def _meta(cls: type) -> _ShapeMeta:
    """Return the ``_ShapeMeta`` sidecar for a Shape, or raise :class:`ShapeError`."""
    meta = getattr(cls, "__chirp_shape__", None)
    if not isinstance(meta, _ShapeMeta):
        msg = (
            f"{getattr(cls, '__name__', cls)!r} is not a @shape-decorated dataclass. "
            'Decorate it with @shape("SELECT ...") before calling Shape.fetch().'
        )
        raise ShapeError(msg)
    return meta


def _bind_params(sql: str, driver: str, params: Mapping[str, Any]) -> tuple[str, tuple[Any, ...]]:
    """Translate ``:name`` placeholders to the driver placeholder.

    SQLite uses ``?`` (positional), PostgreSQL uses ``$N`` (1-based). Returns the
    rewritten SQL plus the params tuple ordered to match the rewritten
    placeholders. Parameters are NEVER concatenated into the SQL text — only the
    placeholder token is rewritten, so this stays injection-safe (S608).

    A ``:name`` appearing more than once reuses the same value: SQLite repeats
    the value in the params tuple (one ``?`` per occurrence); PostgreSQL reuses
    the same ``$N`` for every occurrence (one value per distinct name).
    """
    is_pg = driver != "sqlite"
    ordered: list[Any] = []
    pg_index: dict[str, int] = {}
    out: list[str] = []
    i = 0
    n = len(sql)
    while i < n:
        ch = sql[i]
        # PostgreSQL ``::cast`` is not a placeholder — pass it through verbatim.
        if ch == ":" and i + 1 < n and sql[i + 1] == ":":
            out.append("::")
            i += 2
            continue
        if ch == ":" and i + 1 < n and (sql[i + 1].isalpha() or sql[i + 1] == "_"):
            j = i + 1
            while j < n and (sql[j].isalnum() or sql[j] == "_"):
                j += 1
            pname = sql[i + 1 : j]
            if pname not in params:
                msg = (
                    f"Shape SQL references placeholder :{pname} but no value was "
                    f"passed. Pass it as a keyword argument to Shape.fetch(...)."
                )
                raise ShapeError(msg)
            if is_pg:
                if pname not in pg_index:
                    pg_index[pname] = len(pg_index) + 1
                    ordered.append(params[pname])
                out.append(f"${pg_index[pname]}")
            else:
                ordered.append(params[pname])
                out.append("?")
            i = j
            continue
        out.append(ch)
        i += 1
    return "".join(out), tuple(ordered)


# --- Tenant scope (#169): structural injection on the COMPILER OUTPUT. ---
#
# Per the blueprint §8.1 BLOCKER: the tenant-scope guarantee is delivered by
# STRUCTURALLY INJECTING the scope predicate into every compiled statement and
# asserting on the compiler's OUTPUT -- never by a flaky WHERE-column scanner.
# A scoped shape whose SQL cannot be safely injected (CTE / UNION / SELECT * /
# dynamic) fails loud at startup.

# A scoped shape's SQL is "injectable" only when it is the same simple
# single-SELECT shape _parse_select_columns trusts: no CTE (WITH), no compound
# (UNION/INTERSECT/EXCEPT). We additionally require a recognizable FROM so the
# WHERE clause can be located.
_FROM_RE = re.compile(r"\bFROM\b", re.IGNORECASE)
_WHERE_RE = re.compile(r"\bWHERE\b", re.IGNORECASE)
# Clauses that may legally follow a WHERE; the scope predicate must be inserted
# BEFORE them so it lands inside the WHERE, not after GROUP BY / ORDER BY etc.
_POST_WHERE_RE = re.compile(
    r"\b(GROUP\s+BY|HAVING|ORDER\s+BY|LIMIT|OFFSET|FETCH|WINDOW|RETURNING)\b",
    re.IGNORECASE,
)


def _scope_injectable(sql: str) -> bool:
    """Return whether the scope predicate can be safely structurally injected.

    Un-injectable (opaque) when the SQL is a CTE (``WITH``), a compound query
    (``UNION``/``INTERSECT``/``EXCEPT``), a ``SELECT *`` / expression projection
    the injector cannot reason about (``_parse_select_columns`` returns
    ``None``), or lacks an analyzable ``FROM``. A scoped shape that is
    un-injectable fails loud at startup (never a silently-unscoped query). This
    is the §8.1 boundary: ``CTE / UNION / SELECT * / dynamic`` cannot be
    injected, so the compiler must refuse rather than ship an unscoped query.
    """
    if re.match(r"\s*WITH\b", sql, re.IGNORECASE):
        return False
    if re.search(r"\b(?:UNION|INTERSECT|EXCEPT)\b", sql, re.IGNORECASE):
        return False
    if _FROM_RE.search(sql) is None:
        return False
    # Opaque projection (SELECT * / expression) -> cannot safely scope-inject.
    return _parse_select_columns(sql) is not None


def _has_scope_predicate(sql: str, scope: str) -> bool:
    """Return whether ``sql`` already constrains the scope column to ``:scope``.

    Matches ``<scope> = :scope`` (whitespace-tolerant, optional table qualifier)
    so the compiler does not double-inject a predicate the author already wrote.
    """
    pattern = rf"(?:\w+\.)?{re.escape(scope)}\s*=\s*:scope\b"
    return re.search(pattern, sql, re.IGNORECASE) is not None


def _inject_scope(sql: str, scope: str) -> str:
    """Structurally inject ``<scope> = :scope`` into ``sql``'s WHERE clause.

    Idempotent: returns ``sql`` unchanged when the predicate is already present.
    Adds ``AND <scope> = :scope`` to an existing WHERE (before any GROUP BY /
    ORDER BY / LIMIT tail), or a fresh ``WHERE <scope> = :scope`` after the FROM
    target when no WHERE exists. Raises :class:`ShapeError` when ``sql`` is
    un-injectable (caller should have validated first).
    """
    if _has_scope_predicate(sql, scope):
        return sql
    if not _scope_injectable(sql):
        msg = (
            f"@shape declares scope={scope!r} but its SQL is opaque "
            "(CTE / UNION / no analyzable FROM); the tenant-scope predicate "
            "cannot be structurally injected. Rewrite the SQL as a simple "
            f"single SELECT and add 'WHERE {scope} = :scope' explicitly."
        )
        raise ShapeError(msg)
    predicate = f"{scope} = :scope"
    where_match = _WHERE_RE.search(sql)
    if where_match is not None:
        # Insert ``AND <pred>`` right after the existing WHERE keyword's clause,
        # before any GROUP BY / ORDER BY / LIMIT tail.
        tail_match = _POST_WHERE_RE.search(sql, where_match.end())
        insert_at = tail_match.start() if tail_match is not None else len(sql)
        head = sql[:insert_at].rstrip()
        tail = sql[insert_at:]
        joiner = " " if tail else ""
        return f"{head} AND {predicate}{joiner}{tail}".rstrip()
    # No WHERE: add one after the FROM target, before any tail clause.
    tail_match = _POST_WHERE_RE.search(sql)
    insert_at = tail_match.start() if tail_match is not None else len(sql)
    head = sql[:insert_at].rstrip()
    tail = sql[insert_at:]
    joiner = " " if tail else ""
    return f"{head} WHERE {predicate}{joiner}{tail}".rstrip()


def _compiled_statement(meta: _ShapeMeta) -> str:
    """Return the parent SELECT after scope injection (the compiler's output)."""
    if meta.scope is None:
        return meta.sql
    return _inject_scope(meta.sql, meta.scope)


class Shape:
    """Execution surface for ``@shape``-decorated row models.

    Not instantiated directly — the decorated dataclass *is* the shape. The
    classmethod accessors expose the declared metadata, and the async
    ``fetch`` / ``fetch_one`` / ``stream`` methods run the declared SQL behind
    the :class:`~chirp.data.database.Database` facade (the repository seam).
    """

    @staticmethod
    def sql(cls: type) -> str:
        """Return the declared SQL for a Shape."""
        return _meta(cls).sql

    @staticmethod
    def columns(cls: type) -> tuple[str, ...]:
        """Return the parsed SELECT output columns (``()`` when opaque)."""
        return _meta(cls).columns

    @staticmethod
    def computed(cls: type) -> frozenset[str]:
        """Return the declared computed/derived members."""
        return _meta(cls).computed

    @staticmethod
    def validate(cls: type) -> None:
        """Assert the compiler's OUTPUT honors the Shape's declared scope (#169).

        Called at startup (from the ``shapecheck`` pass). The tenant-scope
        guarantee is delivered by structural injection, so this asserts the
        *compiler output*, not the declared WHERE: for a scoped shape, the
        compiled parent statement AND every batched child ``IN``-list query MUST
        contain the scope predicate. A scoped shape whose SQL is opaque /
        un-injectable raises :class:`ShapeError` (fail-loud at startup) -- the
        compiler cannot inject the predicate, so the query would silently leak
        across tenants. This is the §8.1 BLOCKER guarantee: assert on output,
        never WHERE-scan.

        Also fails loud when a declared nested child is unexpressible by the
        bounded compiler (its ``on`` column cannot be batched into an ``IN``
        list -- e.g. an opaque child SQL).
        """
        meta = _meta(cls)
        if meta.scope is not None:
            compiled = _compiled_statement(meta)
            if not _has_scope_predicate(compiled, meta.scope):  # pragma: no cover
                # _compiled_statement either injects or raises; this is a
                # defensive backstop so an un-asserted output never ships.
                msg = (
                    f"Shape {meta.name!r} declares scope={meta.scope!r} but its "
                    "compiled statement does not contain the scope predicate."
                )
                raise ShapeError(msg)
        for child in meta.nested:
            child_meta = _meta(child.cls)
            # The child must be batchable: its SQL must accept a WHERE on ``on``.
            # A scoped child also threads :scope; validate its compiled form too.
            if child_meta.scope is not None and not _scope_injectable(child_meta.sql):
                msg = (
                    f"Nested child {child_meta.name!r} of {meta.name!r} declares "
                    f"scope={child_meta.scope!r} but its SQL is opaque and the "
                    "scope predicate cannot be injected."
                )
                raise ShapeError(msg)
            if not _scope_injectable(child_meta.sql):
                msg = (
                    f"Nested child {child_meta.name!r} of {meta.name!r} is "
                    "unexpressible by the bounded compiler: its SQL is opaque "
                    "(CTE / UNION / no analyzable FROM), so the batched "
                    f"'WHERE {child.on} IN (...)' query cannot be built. Rewrite "
                    "it as a simple single SELECT."
                )
                raise ShapeError(msg)
            # The child must carry the ``on`` join column as a field so the
            # compiler can group child rows by it. A child that does not SELECT
            # (and declare) ``on`` is unexpressible -> fail loud at startup.
            child_fields = {f.name for f in dataclasses.fields(child.cls)}
            if child.on not in child_fields:
                msg = (
                    f"Nested child {child_meta.name!r} of {meta.name!r} must carry "
                    f"its join column {child.on!r} as a dataclass field so the "
                    f"bounded compiler can group children by it. Add {child.on!r} "
                    "to the child SELECT and the child dataclass."
                )
                raise ShapeError(msg)
            # The parent must carry the ``key`` field the IN-list seeds from.
            parent_fields = {f.name for f in dataclasses.fields(cls)}
            if child.key not in parent_fields:
                msg = (
                    f"Nested child {child_meta.name!r} of {meta.name!r} joins on "
                    f"parent key {child.key!r}, but {meta.name!r} has no such "
                    f"field. Add {child.key!r} to the parent SELECT."
                )
                raise ShapeError(msg)

    @staticmethod
    async def fetch(cls: type[T], db: Database, /, **params: Any) -> list[T]:
        """Run the Shape's SQL and return all rows as frozen dataclasses.

        Scope-injects when the Shape declares ``scope=`` (the ``:scope`` value is
        threaded from ``params``). When the Shape declares ``nested()`` children,
        delegates to the bounded compiler (:func:`_fetch_nested`).

        Usage::

            boards = await Shape.fetch(BoardView, db, id=42)
        """
        meta = _meta(cls)
        if meta.nested:
            return await _fetch_nested(cls, db, params)
        sql, ordered = _bind_params(_compiled_statement(meta), db._driver, params)
        return await db.fetch(cls, sql, *ordered)

    @staticmethod
    async def fetch_one(cls: type[T], db: Database, /, **params: Any) -> T | None:
        """Run the Shape's SQL and return the first row, or ``None``."""
        meta = _meta(cls)
        if meta.nested:
            rows = await _fetch_nested(cls, db, params)
            return rows[0] if rows else None
        sql, ordered = _bind_params(_compiled_statement(meta), db._driver, params)
        return await db.fetch_one(cls, sql, *ordered)

    @staticmethod
    async def stream(cls: type[T], db: Database, /, **params: Any) -> AsyncIterator[T]:
        """Run the Shape's SQL and yield rows incrementally as frozen dataclasses.

        Streaming is incompatible with nested assembly (the bounded compiler must
        buffer parent rows to batch children), so a Shape with ``nested()``
        children raises :class:`ShapeError` -- use :meth:`fetch` instead.
        """
        meta = _meta(cls)
        if meta.nested:
            msg = (
                f"Shape {meta.name!r} declares nested() children and cannot be "
                "streamed (the bounded compiler buffers parent rows to batch "
                "children). Use Shape.fetch() instead."
            )
            raise ShapeError(msg)
        sql, ordered = _bind_params(_compiled_statement(meta), db._driver, params)
        async for row in db.stream(cls, sql, *ordered):
            yield row


# =============================================================================
# Bounded nested compiler (#167) — IN-list batched, O(depth), independent of N.
# =============================================================================


def _child_head(sql: str) -> str:
    """Return the ``SELECT ... FROM <target>`` head of a child SQL, sans WHERE.

    The bounded compiler replaces the child's per-parent join predicate with a
    single batched ``WHERE {on} IN (...)``, so we strip everything from the
    child's own ``WHERE`` onward (the declared join predicate is supplanted by
    the IN-list). Trailing tail clauses (``ORDER BY`` etc.) before any WHERE are
    preserved by leaving them attached to the head only when no WHERE exists.
    """
    where_match = _WHERE_RE.search(sql)
    if where_match is not None:
        return sql[: where_match.start()].rstrip()
    # No WHERE: keep the head up to any tail clause so the IN-list lands in a
    # fresh WHERE before ORDER BY / LIMIT.
    tail_match = _POST_WHERE_RE.search(sql)
    if tail_match is not None:
        return sql[: tail_match.start()].rstrip()
    return sql.rstrip()


def _batched_child_sql(
    child_meta: _ShapeMeta, on: str, key_count: int
) -> tuple[str, tuple[str, ...]]:
    """Build the ONE batched ``IN``-list query for a child level.

    Returns the SQL and the ordered tuple of generated key placeholder names
    (``k0``, ``k1``, ...). The child's per-parent join predicate is replaced by
    a single ``WHERE {on} IN (...)``. When the child declares ``scope=``, the
    scope predicate is structurally injected too (every child statement scoped).
    """
    head = _child_head(child_meta.sql)
    key_names = tuple(f"k{i}" for i in range(key_count))
    placeholders = ", ".join(f":{kn}" for kn in key_names)
    sql = f"{head} WHERE {on} IN ({placeholders})"
    if child_meta.scope is not None:
        sql = _inject_scope(sql, child_meta.scope)
    return sql, key_names


async def _resolve_children(
    parents: list[Any],
    child: NestedShape,
    db: Database,
    params: Mapping[str, Any],
) -> list[Any]:
    """Run ONE batched ``IN``-list query for ``child`` and attach to ``parents``.

    Collects the distinct parent ``key`` values, runs a single query
    (``WHERE {on} IN (...)``), groups child rows by their ``on`` value, recurses
    into the child's own nested children (still one query per grandchild level),
    and rebuilds each parent via :func:`dataclasses.replace` (frozen-safe).

    Returns the list of parents with the nested field populated. Total queries
    for this level is exactly ONE, independent of ``len(parents)``.
    """
    # Distinct, order-stable parent keys (skip None for optional children).
    key_values: list[Any] = []
    seen: set[Any] = set()
    for parent in parents:
        kv = getattr(parent, child.key, None)
        if kv is None:
            continue
        if kv not in seen:
            seen.add(kv)
            key_values.append(kv)

    child_meta = _meta(child.cls)

    if not key_values:
        # No keys to batch (e.g. all-optional-None) -> attach empty tuples.
        return [dataclasses.replace(p, **{child.field: ()}) for p in parents]

    sql_template, key_names = _batched_child_sql(child_meta, child.on, len(key_values))
    child_params: dict[str, Any] = dict(zip(key_names, key_values, strict=True))
    # Thread the tenant scope value through to the child IN-list query.
    if child_meta.scope is not None and "scope" in params:
        child_params["scope"] = params["scope"]
    sql, ordered = _bind_params(sql_template, db._driver, child_params)
    child_rows = await db.fetch(child.cls, sql, *ordered)

    # Recurse: a grandchild level is still ONE query (over ALL child rows).
    if child_meta.nested:
        for grandchild in child_meta.nested:
            child_rows = await _resolve_children(child_rows, grandchild, db, params)

    # Group children by their ``on`` value.
    grouped: dict[Any, list[Any]] = {}
    for row in child_rows:
        grouped.setdefault(getattr(row, child.on), []).append(row)

    # Frozen rebuild: attach the grouped tuple to each parent.
    return [
        dataclasses.replace(
            parent,
            **{child.field: tuple(grouped.get(getattr(parent, child.key, None), ()))},
        )
        for parent in parents
    ]


async def _fetch_nested[T](cls: type[T], db: Database, params: Mapping[str, Any]) -> list[T]:
    """Bounded nested loader: 1 parent query + 1 query per declared child level.

    Runs the parent SELECT (scope-injected when declared), then for EACH declared
    child level runs ONE batched ``IN``-list query (never per parent row). Total
    queries = ``1 + num_child_levels`` -- bounded, ``O(depth)``, independent of
    the parent row count ``N`` (the #167 no-N+1 guarantee).
    """
    meta = _meta(cls)
    sql, ordered = _bind_params(_compiled_statement(meta), db._driver, params)
    parents: list[Any] = await db.fetch(cls, sql, *ordered)
    for child in meta.nested:
        parents = await _resolve_children(parents, child, db, params)
    return parents


# =============================================================================
# Page-composite (#170) + repository seam (#171).
# =============================================================================
#
# A *Composite* aggregates several Shapes for one page so the page declares its
# data ONCE. ``Composite.load`` runs the batched query set across the member
# Shapes (reusing the L3 bounded compiler for nested members), coalescing the
# shared tenant scope + params, and returns ONE frozen instance.
#
# Repository seam (#171): there is NO public render-time API that accepts a raw
# SQL string. SQL lives only on the @shape/@composite declarations (co-located
# with the row model and the block); the compiled SQL materializes behind
# ``Shape.fetch`` / ``Composite.load`` (the Database facade). The frozen result
# -- never a SQL string -- is what reaches the template.


@dataclasses.dataclass(frozen=True, slots=True)
class _CompositeMember:
    """One field of a ``@composite`` resolved to its member Shape.

    Attributes:
        field: The composite dataclass field name (the template variable).
        shape_cls: The member ``@shape``-decorated row model.
        is_sequence: ``True`` when the field is a ``tuple[Shape, ...]`` (fetch
            all rows); ``False`` when it is a single ``Shape`` (fetch one row).
    """

    field: str
    shape_cls: type
    is_sequence: bool


@dataclasses.dataclass(frozen=True, slots=True)
class _CompositeMeta:
    """Immutable sidecar describing a ``@composite``-decorated dataclass.

    Attached to the class as ``cls.__chirp_composite__`` once at decoration and
    never mutated (frozen-clean for free-threaded 3.14t).

    Attributes:
        members: The resolved member Shapes, one per composite field.
        scope: The composite-level tenant scope key (#169), or ``None``. When
            set, it is threaded to every member Shape that declares a matching
            ``scope=`` (the page scopes once; members inherit).
        name: Registry / diagnostic name (defaults to ``cls.__name__``).
    """

    members: tuple[_CompositeMember, ...]
    scope: str | None
    name: str


def _resolve_member_shape(annotation: Any) -> tuple[type, bool] | None:
    """Resolve a composite field annotation to ``(shape_cls, is_sequence)``.

    A composite field is either a single ``@shape`` class (single-object load)
    or a ``tuple[Shape, ...]`` (sequence load). Returns ``None`` when the
    annotation is neither (the field is not a Shape member -- fail loud at
    decoration in :func:`composite`). ``Optional`` single Shapes
    (``Shape | None``) are accepted and load one row (or ``None``).
    """
    # Unwrap Optional (Shape | None) -> the single non-None branch.
    origin = get_origin(annotation)
    if origin is _types.UnionType:
        branches = [a for a in get_args(annotation) if a is not type(None)]
        if len(branches) == 1:
            annotation = branches[0]
            origin = get_origin(annotation)

    # tuple[Shape, ...] -> sequence member.
    if origin is tuple:
        args = get_args(annotation)
        if not args:
            return None
        inner = args[0]
        if isinstance(inner, type) and _shape_or_none(inner) is not None:
            return inner, True
        return None

    # Bare Shape class -> single-object member.
    if isinstance(annotation, type) and _shape_or_none(annotation) is not None:
        return annotation, False
    return None


def _shape_or_none(cls: Any) -> _ShapeMeta | None:
    """Return the ``_ShapeMeta`` sidecar for ``cls``, or ``None`` if not a Shape."""
    meta = getattr(cls, "__chirp_shape__", None)
    return meta if isinstance(meta, _ShapeMeta) else None


def _collect_members(cls: type) -> tuple[_CompositeMember, ...]:
    """Resolve every composite field to a member Shape (fail loud otherwise).

    Uses :func:`typing.get_type_hints` so string annotations (``from __future__
    import annotations``) resolve to real classes. A field whose type is neither
    a ``@shape`` class nor a ``tuple[Shape, ...]`` raises :class:`ShapeError` at
    decoration -- a composite member must be a Shape (the page's data is declared
    once, in terms of Shapes).
    """
    try:
        hints = typing.get_type_hints(cls)
    except Exception as exc:
        msg = (
            f"@composite on {cls.__name__} could not resolve its field type hints "
            f"({exc}). Ensure every member type is importable in the class's module."
        )
        raise ShapeError(msg) from exc
    members: list[_CompositeMember] = []
    for f in dataclasses.fields(cls):
        annotation = hints.get(f.name, f.type)
        resolved = _resolve_member_shape(annotation)
        if resolved is None:
            msg = (
                f"@composite field {f.name!r} on {cls.__name__} is not a Shape "
                f"member. Each composite field must be a @shape-decorated class "
                "or a tuple[Shape, ...]. The page declares its data once, in terms "
                "of Shapes."
            )
            raise ShapeError(msg)
        shape_cls, is_sequence = resolved
        members.append(_CompositeMember(field=f.name, shape_cls=shape_cls, is_sequence=is_sequence))
    return tuple(members)


def composite(*, scope: str | None = None) -> Any:
    """Aggregate several Shapes for one page into a single frozen dataclass (#170).

    The decorated dataclass declares the page's data ONCE: each field is a member
    ``@shape`` class (single object) or ``tuple[Shape, ...]`` (a list). Run the
    whole page behind the repository seam via :meth:`Composite.load`, which fans
    out to the member Shapes (reusing the L3 bounded compiler for nested members),
    coalesces the shared tenant ``scope`` + params, and returns one frozen
    instance::

        @composite(scope="community_id")
        @dataclass(frozen=True, slots=True)
        class BoardPage:
            board: Board                  # single-object member
            members: tuple[Member, ...]   # sequence member
            activity: tuple[Event, ...]

        page = await Composite.load(BoardPage, db, board_id=7, scope=1)

    Args:
        scope: Composite-level tenant scope key. When set, the ``:scope`` value
            (threaded from ``Composite.load(..., scope=...)``) is passed to every
            member Shape that declares a matching ``scope=`` -- the page scopes
            once; the members inherit it.

    Raises:
        ShapeError: if the target is not a frozen, slotted dataclass, or any
            field is not a Shape member.
    """

    def decorate(cls: type[T]) -> type[T]:
        _validate_target(cls)
        members = _collect_members(cls)
        meta = _CompositeMeta(members=members, scope=scope, name=cls.__name__)
        # Attach the frozen sidecar once at decoration (immutable thereafter).
        setattr(cls, "__chirp_composite__", meta)  # noqa: B010 — dynamic sentinel attr
        return cls

    return decorate


def _composite_meta(cls: type) -> _CompositeMeta:
    """Return the ``_CompositeMeta`` sidecar for a Composite, or raise ``ShapeError``."""
    meta = getattr(cls, "__chirp_composite__", None)
    if not isinstance(meta, _CompositeMeta):
        msg = (
            f"{getattr(cls, '__name__', cls)!r} is not a @composite-decorated dataclass. "
            "Decorate it with @composite() before calling Composite.load()."
        )
        raise ShapeError(msg)
    return meta


class Composite:
    """Load surface for ``@composite``-decorated page models (#170, #171).

    Not instantiated directly -- the decorated dataclass *is* the page model.
    :meth:`load` runs the batched query set across the member Shapes behind the
    :class:`~chirp.data.database.Database` facade (the repository seam): SQL never
    leaves the ``@shape``/``@composite`` declarations, and the frozen result -- not
    a SQL string -- is what reaches the template.
    """

    @staticmethod
    async def load(cls: type[T], db: Database, /, **params: Any) -> T:
        """Run the batched query set for every member Shape and return one frozen instance.

        Each member Shape is loaded behind the ``Database`` facade (single-object
        members via :meth:`Shape.fetch_one`, sequence members via
        :meth:`Shape.fetch`; nested members reuse the L3 bounded compiler). The
        shared ``scope`` + ``params`` are coalesced -- threaded to every member
        that declares a matching ``scope=`` -- so the page declares its tenant
        scope once and the members inherit it. Returns one frozen ``cls``.

        Usage::

            page = await Composite.load(BoardPage, db, board_id=7, scope=1)
        """
        meta = _composite_meta(cls)
        values: dict[str, Any] = {}
        for member in meta.members:
            member_meta = _meta(member.shape_cls)
            member_params = _member_params(member_meta, meta.scope, params)
            if member.is_sequence:
                values[member.field] = tuple(
                    await Shape.fetch(member.shape_cls, db, **member_params)
                )
            else:
                values[member.field] = await Shape.fetch_one(member.shape_cls, db, **member_params)
        return cls(**values)  # type: ignore[call-arg]


def _member_params(
    member_meta: _ShapeMeta,
    composite_scope: str | None,
    params: Mapping[str, Any],
) -> dict[str, Any]:
    """Coalesce the shared scope + params for one member Shape's load.

    Only the placeholders the member's compiled SQL actually references are
    passed (so an unrelated page param does not error a member whose SQL never
    names it). The tenant ``:scope`` value is threaded when the member declares
    ``scope=`` -- the composite-level scope is the page's single declaration; the
    member inherits it.
    """
    needed = _placeholder_names(_compiled_statement(member_meta))
    # A scoped member always references :scope after structural injection.
    if member_meta.scope is not None:
        needed.add("scope")
    member_params = {k: v for k, v in params.items() if k in needed}
    return member_params


def _placeholder_names(sql: str) -> set[str]:
    """Return the set of ``:name`` placeholder names referenced by ``sql``.

    Mirrors :func:`_bind_params`'s scanner (``::cast`` is not a placeholder) so
    the coalescer asks for exactly the params each member statement binds.
    """
    names: set[str] = set()
    i = 0
    n = len(sql)
    while i < n:
        ch = sql[i]
        if ch == ":" and i + 1 < n and sql[i + 1] == ":":
            i += 2
            continue
        if ch == ":" and i + 1 < n and (sql[i + 1].isalpha() or sql[i + 1] == "_"):
            j = i + 1
            while j < n and (sql[j].isalnum() or sql[j] == "_"):
                j += 1
            names.add(sql[i + 1 : j])
            i = j
            continue
        i += 1
    return names
