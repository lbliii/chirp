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
from collections.abc import AsyncIterator, Iterator, Mapping, Sequence
from typing import TYPE_CHECKING, Any, TypeVar, get_args, get_origin

from chirp.contracts.rules_data_shapes import _parse_select_columns, _strip_sql_comments
from chirp.data.errors import ShapeError

if TYPE_CHECKING:
    from chirp.data.database import Database

T = TypeVar("T")

# Metadata key carrying a NestedShape on a dataclass field (see nested()).
_NESTED_META_KEY = "chirp_nested"

# Reserved placeholder-name prefix owned exclusively by the compiler. The
# bounded nested compiler generates batch-key placeholders (``__chirp_k0`` ...)
# and the per-parent-LIMIT window column (``__chirp_rn``) under this prefix so
# they can never collide with an author placeholder (finding R3-2). An author
# whose DECLARED SQL writes a ``:__chirp_...`` placeholder reintroduces the exact
# collision the prefix was reserved to prevent: ``Shape.validate`` would PASS,
# but ``Shape.fetch`` would bind the author's placeholder to a compiler-generated
# value (e.g. a parent-key value seeded into the IN-list), silently returning
# wrong/empty rows. The author's declared SQL never legitimately contains a
# ``__chirp_`` name (they are compiler-generated), so a fail-loud guard on the
# declared placeholders is safe and precise (finding F1).
_RESERVED_PLACEHOLDER_PREFIX = "__chirp_"

# Maximum parent keys per batched ``IN``-list query (#167 chunking; finding #5).
#
# SQLite's compile-time ``SQLITE_MAX_VARIABLE_NUMBER`` floor is 999 on older
# builds; 900 sits safely below it with explicit headroom for the scope param
# (``:scope``) and an optional per-parent-LIMIT window param (``:limit``).
# PostgreSQL's limit is far higher (65535), so 900 is safe on both backends.
# A query over more parent keys than this is chunked into multiple batches and
# merged -- the query count stays O(chunks) per child level, independent of the
# child ROW count. Module-level so a test can monkeypatch it to a small value
# (e.g. 2) and prove chunking without seeding tens of thousands of rows; the
# chunking loop MUST read it as a module global at call time, never capture it
# as a default argument.
_MAX_IN_LIST_KEYS: int = 900


def _skip_inert(sql: str, i: int) -> int | None:
    """If a string literal or SQL comment begins at ``sql[i]``, skip past it.

    The single, shared low-level "inert span" skipper consulted by EVERY scanner
    in this module (:func:`_scan_placeholders`, :func:`_iter_sql_tokens`, and the
    depth bookkeeping that consumes :func:`_iter_sql_tokens`). Routing every
    scanner through one skipper removes the parallel-maintenance hazard between
    them and -- critically -- makes them all comment-aware in lockstep (finding
    A2): a ``:name`` token, a paren, or a clause keyword that lives inside a
    string literal or a comment is NOT real SQL and must never drive placeholder
    binding, paren depth, or clause detection.

    Recognized inert spans:

    * **String literals** (``'...'`` / ``"..."``), honoring doubled-quote
      escapes (``''`` / ``""``) so a colon inside a time literal like
      ``':30:00'`` stays inside the string.
    * **Line comments** (``-- ... EOL``) -- consumed through the next newline
      (the newline itself is left for the caller).
    * **Block comments** (``/* ... */``) -- consumed through the closing ``*/``.
      Per the SQL standard these do NOT nest, so the first ``*/`` closes the
      comment. An unterminated block comment runs to end-of-string.

    Returns the index ONE PAST the inert span when one started at ``i``, or
    ``None`` when ``sql[i]`` does not begin an inert span (the caller advances
    normally). Always returns a value ``> i`` when non-``None`` so no caller can
    livelock.
    """
    n = len(sql)
    ch = sql[i]
    # String literal: skip its body, honoring doubled-quote escapes.
    if ch == "'" or ch == '"':
        quote = ch
        j = i + 1
        while j < n:
            if sql[j] == quote:
                if j + 1 < n and sql[j + 1] == quote:
                    j += 2  # doubled-quote escape -> stays inside the string
                    continue
                return j + 1  # closing quote consumed
            j += 1
        return n  # unterminated string -> consume to EOF
    # Line comment: ``--`` to end of line (newline left for the caller).
    if ch == "-" and i + 1 < n and sql[i + 1] == "-":
        j = i + 2
        while j < n and sql[j] != "\n":
            j += 1
        return j
    # Block comment: ``/* ... */`` (non-nesting per the SQL standard).
    if ch == "/" and i + 1 < n and sql[i + 1] == "*":
        j = i + 2
        while j < n:
            if sql[j] == "*" and j + 1 < n and sql[j + 1] == "/":
                return j + 2
            j += 1
        return n  # unterminated block comment -> consume to EOF
    return None


def _paren_depth_at(sql: str, target: int) -> int | None:
    """Return the parenthesis depth at index ``target``, or ``None`` if inert.

    Walks ``sql[:target]`` skipping string literals and SQL comments via
    :func:`_skip_inert`, counting only REAL ``(`` / ``)``. Used to confirm a
    regex match sits at depth 0 without a second, drift-prone hand-rolled depth
    loop (finding A2: the two former depth counters could desync).

    Returns ``None`` when ``target`` lands INSIDE an inert span -- a string
    literal or a SQL comment (finding A2 leak: a ``community_id = :scope``
    written inside a ``-- ...`` comment is NOT a real predicate and must never be
    treated as already-scoped, which would suppress injection and ship an
    unscoped query). A ``None`` result means "this regex match is not real SQL;
    skip it." Otherwise returns the real paren depth at ``target``.
    """
    depth = 0
    i = 0
    n = len(sql)
    while i < target and i < n:
        skipped = _skip_inert(sql, i)
        if skipped is not None:
            # ``target`` falls inside this inert span -> the match is not real SQL.
            if skipped > target:
                return None
            i = skipped
            continue
        ch = sql[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        i += 1
    return depth


def _scan_placeholders(sql: str) -> Iterator[tuple[str, int, int]]:
    """Yield ``(name, start, end)`` spans for each ``:name`` placeholder in ``sql``.

    The single, shared placeholder scanner consumed by both :func:`_bind_params`
    (which rewrites spans to the driver placeholder) and :func:`_placeholder_names`
    (which collects the distinct names). Factoring one scanner removes the
    parallel-maintenance hazard between the two callers (finding #8).

    It is:

    * **cast-aware** -- a PostgreSQL ``::cast`` operator is not a placeholder and
      yields nothing (the scanner advances past both colons);
    * **quoted-string aware** -- a ``:name``-shaped token *inside* a string
      literal (``'...'`` or ``"..."``) is NOT a placeholder. The scanner skips
      string bodies, honoring doubled-quote escapes (``''`` / ``""``), so a colon
      inside a time literal like ``':30:00'`` or an interval string is never
      misparsed as a bind placeholder.
    * **comment-aware** (finding A2) -- a ``:name``-shaped token inside a SQL
      line comment (``-- ...``) or block comment (``/* ... */``) is NOT a
      placeholder, so a commented note never becomes a phantom bind param.

    A name is ``[A-Za-z_][A-Za-z0-9_]*`` immediately following a single ``:``.
    Spans are yielded left-to-right; ``start`` is the index of the ``:`` and
    ``end`` is one past the last name character (so ``sql[start:end]`` is the
    full ``:name`` token).
    """
    i = 0
    n = len(sql)
    while i < n:
        # Skip string literals and comments so a ``:name``-shaped token inside
        # one is not a placeholder (the shared inert-span skipper).
        skipped = _skip_inert(sql, i)
        if skipped is not None:
            i = skipped
            continue
        ch = sql[i]
        # PostgreSQL ``::cast`` is not a placeholder -- advance past both colons.
        if ch == ":" and i + 1 < n and sql[i + 1] == ":":
            i += 2
            continue
        if ch == ":" and i + 1 < n and (sql[i + 1].isalpha() or sql[i + 1] == "_"):
            j = i + 1
            while j < n and (sql[j].isalnum() or sql[j] == "_"):
                j += 1
            yield sql[i + 1 : j], i, j
            i = j
            continue
        i += 1


def _reject_reserved_placeholders(sql: str, *, shape_name: str) -> None:
    """Fail loud when ``sql`` declares a ``:__chirp_...`` placeholder (finding F1).

    The ``__chirp_`` prefix is reserved for compiler-generated placeholders
    (``__chirp_k0`` batch keys, ``__chirp_rn`` window rank). An author placeholder
    under this prefix would silently collide with a compiler-generated value at
    fetch time -- ``Shape.validate`` passes, but ``Shape.fetch`` binds the
    author's ``:__chirp_k0`` to the parent-key value seeded into the IN-list,
    returning wrong/empty rows. The author's declared SQL never legitimately
    contains a ``__chirp_`` placeholder, so this guard is precise: it scans the
    DECLARED SQL's placeholders via the shared :func:`_scan_placeholders` (which
    is comment- and string-literal-aware, so a ``:__chirp_`` token inside a
    comment or string literal is correctly ignored) and raises on the first
    reserved-prefixed author placeholder.
    """
    for name, _, _ in _scan_placeholders(sql):
        if name.startswith(_RESERVED_PLACEHOLDER_PREFIX):
            msg = (
                f"@shape {shape_name!r}: SQL declares placeholder :{name} whose "
                f"name uses the reserved {_RESERVED_PLACEHOLDER_PREFIX!r} prefix. "
                "That prefix is owned by the bounded compiler (generated IN-list "
                "batch keys and the window rank column); an author placeholder "
                "under it would silently bind to a compiler-generated value at "
                "fetch time and return wrong or empty rows. Rename the placeholder "
                f"to anything not beginning with {_RESERVED_PLACEHOLDER_PREFIX!r}."
            )
            raise ShapeError(msg)


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
        # Fail loud (finding F1) if the author's DECLARED SQL uses a placeholder
        # under the compiler-reserved ``__chirp_`` prefix. Applied here at
        # decoration so it covers parent AND every nested-child SQL (each child is
        # itself @shape-decorated), at the earliest point -- the feature's posture.
        _reject_reserved_placeholders(sql, shape_name=name if name is not None else cls.__name__)
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

    Placeholder detection (including ``::cast`` and quoted-string awareness) is
    delegated to the shared :func:`_scan_placeholders` scanner so this stays in
    lockstep with :func:`_placeholder_names` (finding #8).
    """
    is_pg = driver != "sqlite"
    ordered: list[Any] = []
    pg_index: dict[str, int] = {}
    out: list[str] = []
    cursor = 0
    for pname, start, end in _scan_placeholders(sql):
        # Copy the literal text since the previous placeholder verbatim.
        out.append(sql[cursor:start])
        cursor = end
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
    out.append(sql[cursor:])
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
# WHERE clause can be located. Clause-position decisions (where the WHERE is,
# where the trailing GROUP/ORDER/LIMIT tail starts) are made by the paren-depth
# tokenizer below (finding #6) -- a regex cannot tell a depth-0 clause from a
# subquery's clause.
_FROM_RE = re.compile(r"\bFROM\b", re.IGNORECASE)


# A bare SQL identifier/keyword token (used by the paren-depth tokenizer below).
_WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
# Clause keywords that may follow a depth-0 WHERE; the scope predicate is
# inserted BEFORE the first of these so it lands inside the WHERE clause. Stored
# as a frozenset of single + leading-word forms (the two-word GROUP/ORDER BY are
# recognized by their leading keyword at depth 0).
_POST_WHERE_KEYWORDS = frozenset(
    {"GROUP", "HAVING", "ORDER", "LIMIT", "OFFSET", "FETCH", "WINDOW", "RETURNING"}
)


def _iter_sql_tokens(sql: str) -> Iterator[tuple[str, int, int]]:
    """Yield ``(token, depth, start)`` for keyword/identifier tokens in ``sql``.

    A minimal left-to-right tokenizer that tracks parenthesis depth and skips
    quoted-string literals AND SQL comments (so a keyword, paren, or clause
    keyword inside a string or comment is not a token and does not move the depth
    counter -- finding A2). It yields one entry per word token (``[A-Za-z_]\\w*``)
    with the paren depth at the token's opening position. Punctuation and
    parentheses are not yielded; they only adjust ``depth``. The single
    comment-aware tokenizer that ALL depth / clause / placeholder analysis routes
    through, so there is exactly one depth counter (no parallel hand-rolled loop
    that can desync). This is NOT a general SQL parser.
    """
    i = 0
    n = len(sql)
    depth = 0
    while i < n:
        skipped = _skip_inert(sql, i)
        if skipped is not None:
            i = skipped
            continue
        ch = sql[i]
        if ch == "(":
            depth += 1
            i += 1
            continue
        if ch == ")":
            depth -= 1
            i += 1
            continue
        if ch.isalpha() or ch == "_":
            m = _WORD_RE.match(sql, i)
            if m is None:  # pragma: no cover - isalpha() guarantees a match
                i += 1
                continue
            yield m.group(0).upper(), depth, i
            i = m.end()
            continue
        i += 1


def _next_nonspace(sql: str, idx: int) -> str | None:
    """Return the first non-whitespace character at/after ``idx``, or ``None``."""
    while idx < len(sql) and sql[idx].isspace():
        idx += 1
    return sql[idx] if idx < len(sql) else None


def _outer_where_target(sql: str) -> str | None:
    """Classify the OUTER query's WHERE analyzability for scope injection (#6).

    Returns:
        ``"where"`` -- the outer query has exactly one analyzable depth-0 WHERE.
        ``"no_where"`` -- the outer query has no depth-0 WHERE (a fresh one can
            be appended after the FROM target).
        ``None`` -- the SQL is NOT safely scope-injectable: the depth-0 FROM is
            a derived table / FROM-subquery (``FROM (SELECT ...)``), there is a
            depth>0 SELECT sitting in projection/FROM position (a correlated /
            scalar subquery the simple injector cannot reason about), or there is
            more than one depth-0 WHERE.

    This is the paren-depth gate that the old regex-only :func:`_scope_injectable`
    lacked: a regex cannot tell a depth-0 WHERE from a subquery's WHERE, so
    ``SELECT ... FROM (SELECT ... WHERE ...) x`` previously passed and produced
    invalid injected SQL (a silent tenant-scope-shaped bug). Three decisions,
    nothing more (scope-creep guard in data/AGENTS.md).
    """
    seen_outer_from = False
    depth0_where_count = 0
    for kw, depth, start in _iter_sql_tokens(sql):
        if depth == 0 and kw == "FROM" and not seen_outer_from:
            seen_outer_from = True
            from_end = start + len("FROM")
            # A derived table / FROM-subquery: ``FROM (`` at depth 0.
            if _next_nonspace(sql, from_end) == "(":
                return None
            continue
        if depth == 0 and kw == "WHERE":
            depth0_where_count += 1
            continue
        # A SELECT below depth 0 that appears BEFORE the outer FROM is a scalar
        # subquery in the projection; one between FROM and the outer WHERE is a
        # correlated/derived construct. Either way the simple injector cannot
        # reason about it -> reject. A depth>0 SELECT AFTER the outer WHERE is an
        # IN-subquery predicate, which is fine (the depth-0 WHERE is still the
        # injection target).
        if depth > 0 and kw == "SELECT" and (not seen_outer_from or depth0_where_count == 0):
            return None
    if depth0_where_count > 1:
        return None
    if depth0_where_count == 1:
        return "where"
    return "no_where"


def _scope_injectable(sql: str) -> bool:
    """Return whether the scope predicate can be safely structurally injected.

    Un-injectable (opaque) when the SQL is a CTE (``WITH``), a compound query
    (``UNION``/``INTERSECT``/``EXCEPT``), a ``SELECT *`` / expression projection
    the injector cannot reason about (``_parse_select_columns`` returns
    ``None``), lacks an analyzable ``FROM``, or -- per finding #6 -- has an outer
    query whose WHERE/FROM is not a single analyzable target (derived table /
    FROM-subquery / correlated subquery / more than one depth-0 WHERE). A scoped
    shape that is un-injectable fails loud at startup (never a silently-unscoped
    query). This is the §8.1 boundary: ``CTE / UNION / SELECT * / dynamic /
    derived-table`` cannot be injected, so the compiler must refuse rather than
    ship an unscoped query.
    """
    # Run the compound/CTE/FROM keyword gates over COMMENT-STRIPPED SQL (finding
    # F2): a scoped shape whose SQL merely MENTIONS ``WITH``/``UNION``/etc. inside
    # a ``-- ...`` or ``/* ... */`` comment is NOT a compound query and must not be
    # false-rejected as opaque. Reuse the shared string-literal-aware comment
    # stripper from rules_data_shapes (the same one _parse_select_columns uses) --
    # no third hand-rolled comment lexer (finding A2). Offsets are irrelevant here
    # (these gates only need a boolean), so the length-changing strip is safe.
    stripped = _strip_sql_comments(sql)
    if re.match(r"\s*WITH\b", stripped, re.IGNORECASE):
        return False
    if re.search(r"\b(?:UNION|INTERSECT|EXCEPT)\b", stripped, re.IGNORECASE):
        return False
    if _FROM_RE.search(stripped) is None:
        return False
    # Opaque projection (SELECT * / expression) -> cannot safely scope-inject.
    if _parse_select_columns(sql) is None:
        return False
    # Outer-query analyzability gate (#6): reject derived-table / FROM-subquery /
    # correlated-subquery / multi-WHERE outer queries the simple injector cannot
    # reason about.
    return _outer_where_target(sql) is not None


# The compiler's canonical injected scope predicate. Both _has_scope_predicate
# (idempotency) and _inject_scope (author-conflict rejection, finding #7) decide
# on this exact form so the runtime and the validate() backstop agree.
_CANONICAL_SCOPE_VALUE = ":scope"


def _depth0_scope_predicate(sql: str, scope: str) -> str | None:
    """Return the RHS of a depth-0 predicate on the scope column, or ``None``.

    Detects ANY depth-0 constraint on the scope column -- ``<col> = <rhs>``,
    ``<col> IN (...)``, ``<col> = :other`` -- not just the canonical
    ``<col> = :scope`` (finding #7). Returns the matched right-hand side text
    (the canonical form is exactly ``":scope"``); ``None`` when no such depth-0
    predicate exists. A predicate inside a subquery (depth > 0) is ignored so a
    subquery predicate cannot fool the idempotency / conflict decision.

    The scope-column matcher is anchored on BOTH edges (finding A1, the
    tenant-isolation BLOCKER). Without a left boundary, ``scope='community_id'``
    substring-matched the suffix of ``actor_community_id`` and judged a query
    ALREADY scoped -- so the compiler injected nothing and shipped an UNSCOPED
    cross-tenant query, while this same substring match made the
    :meth:`Shape.validate` backstop pass clean. The left lookbehind
    ``(?<![\\w.])`` rejects a preceding word character OR ``.`` (so the column is
    not the tail of ``foo_community_id`` and not a qualified column whose bare
    suffix happens to equal ``scope``), and the right boundary ``(?![\\w])``
    rejects a trailing word character (so ``community_id`` does not match
    ``community_id_archived``).
    """
    # Build a scope-column matcher: optional table qualifier + the scope column,
    # whitespace tolerant, then ``=`` or ``IN``, with BOTH edges anchored so a
    # column whose suffix equals ``scope`` (e.g. ``actor_community_id``) is not a
    # false match. We locate candidate matches via regex, then confirm the match
    # sits at paren depth 0 using the shared inert-span-aware depth bookkeeping
    # (a regex alone cannot tell depth, and the depth walk must skip comments).
    pattern = re.compile(
        rf"(?<![\w.])(?:\w+\.)?{re.escape(scope)}(?![\w])\s*(?:=\s*(\S+)|\bIN\b\s*\([^)]*\))",
        re.IGNORECASE,
    )
    for m in pattern.finditer(sql):
        # A match inside an inert span (string / comment) is not real SQL --
        # _paren_depth_at returns None for it (finding A2: a commented
        # ``community_id = :scope`` must not be treated as an existing predicate).
        if _paren_depth_at(sql, m.start()) == 0:
            rhs = m.group(1)
            return rhs if rhs is not None else "IN"
    return None


def _has_scope_predicate(sql: str, scope: str) -> bool:
    """Return whether ``sql`` already carries the canonical ``<scope> = :scope``.

    Used for idempotency (the compiler does not double-inject its own predicate)
    and as the :meth:`Shape.validate` output backstop. Matches ONLY the compiler's
    canonical depth-0 form ``<scope> = :scope`` (whitespace-tolerant, optional
    table qualifier) -- depth-aware so a subquery-level predicate cannot fool the
    backstop (finding #7). A non-canonical author predicate on the scope column
    is rejected loudly by :func:`_inject_scope`, not silently treated as present.
    """
    rhs = _depth0_scope_predicate(sql, scope)
    return rhs is not None and rhs.rstrip(")").lower() == _CANONICAL_SCOPE_VALUE


def _inject_scope(sql: str, scope: str) -> str:
    """Structurally inject ``<scope> = :scope`` into ``sql``'s WHERE clause.

    Idempotent: returns ``sql`` unchanged when the compiler's own canonical
    predicate is already present. Adds ``AND <scope> = :scope`` to an existing
    depth-0 WHERE (before any GROUP BY / ORDER BY / LIMIT tail), or a fresh
    ``WHERE <scope> = :scope`` after the FROM target when no depth-0 WHERE
    exists. Raises :class:`ShapeError` when ``sql`` is un-injectable (caller
    should have validated first) OR when the author wrote their OWN
    (non-canonical) predicate on the scope column -- the scope guarantee is the
    compiler's, not the author's, so an ambiguous author predicate fails loud
    rather than being silently double-injected (finding #7).
    """
    existing = _depth0_scope_predicate(sql, scope)
    if existing is not None:
        # The compiler's own canonical predicate -> idempotent (no re-inject).
        if existing.rstrip(")").lower() == _CANONICAL_SCOPE_VALUE:
            return sql
        # An author-written scope predicate (different RHS / IN-list). Ambiguous
        # ownership of the tenant-scope guarantee -> fail loud.
        msg = (
            f"@shape declares scope={scope!r} but its SQL already constrains the "
            f"scope column {scope!r} with an author-written predicate. The "
            "tenant-scope guarantee is owned by the compiler (it injects "
            f"'{scope} = :scope'); remove your own predicate on {scope!r} and let "
            "the compiler add it, or drop scope= if you must scope manually."
        )
        raise ShapeError(msg)
    if not _scope_injectable(sql):
        msg = (
            f"@shape declares scope={scope!r} but its SQL is opaque "
            "(CTE / UNION / SELECT * / no analyzable FROM / derived-table "
            "FROM-subquery); the tenant-scope predicate cannot be "
            "structurally injected. Rewrite the SQL as a simple single "
            f"SELECT and add 'WHERE {scope} = :scope' explicitly."
        )
        raise ShapeError(msg)
    # _scope_injectable True guarantees _outer_where_target is non-None.
    target = _outer_where_target(sql)
    predicate = f"{scope} = :scope"
    if target == "where":
        # Insert ``AND <pred>`` before any depth-0 GROUP BY / ORDER BY / LIMIT
        # tail (the depth-0 WHERE is the injection target). The tail boundary
        # (clause keyword OR trailing comment) is sought only AFTER the WHERE
        # keyword so a comment that sits BEFORE the WHERE is not mistaken for the
        # tail (finding A2: ``... /* WHERE x */ WHERE a = :a``). The anchor also
        # skips a comment that sits IMMEDIATELY after WHERE, before the first
        # predicate (finding F3: ``WHERE -- c\n a = :a`` / ``WHERE /* c */ a =
        # :a``) -- otherwise that leading comment is mistaken for the tail and the
        # predicate lands as malformed ``WHERE AND <pred>``.
        insert_at = _depth0_tail_position(
            sql, after=_skip_leading_inert(sql, _depth0_where_position(sql))
        )
        head = sql[:insert_at].rstrip()
        tail = sql[insert_at:]
        joiner = " " if tail else ""
        return f"{head} AND {predicate}{joiner}{tail}".rstrip()
    # No depth-0 WHERE: add one after the FROM target, before any tail clause.
    # The boundary is sought only AFTER the depth-0 FROM target so a comment in
    # the projection list is not mistaken for the tail. The anchor also skips a
    # comment immediately after the FROM target (finding F3) for symmetry with the
    # WHERE path -- a leading comment must not be treated as the tail.
    insert_at = _depth0_tail_position(
        sql, after=_skip_leading_inert(sql, _depth0_from_target_end(sql))
    )
    head = sql[:insert_at].rstrip()
    tail = sql[insert_at:]
    joiner = " " if tail else ""
    return f"{head} WHERE {predicate}{joiner}{tail}".rstrip()


def _first_depth0_comment(sql: str, after: int = 0) -> int | None:
    """Return the start index of the first depth-0 SQL comment at/after ``after``.

    Walks the inert-span-aware character stream and reports where a depth-0
    ``--`` line comment or ``/* ... */`` block comment begins. The scope
    predicate must be inserted BEFORE any trailing comment so the injected
    ``AND <scope> = :scope`` lands in EXECUTABLE SQL, not after a ``--`` (which
    would silently comment out the tenant predicate -- finding A2). A comment
    inside a subquery (depth > 0) -- or one positioned BEFORE ``after`` (e.g. a
    comment in the projection list, ahead of the WHERE) -- is not a boundary for
    the outer injection.
    """
    i = 0
    n = len(sql)
    depth = 0
    while i < n:
        ch = sql[i]
        is_comment = (ch == "-" and i + 1 < n and sql[i + 1] == "-") or (
            ch == "/" and i + 1 < n and sql[i + 1] == "*"
        )
        if is_comment and depth == 0 and i >= after:
            return i
        skipped = _skip_inert(sql, i)
        if skipped is not None:
            i = skipped
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        i += 1
    return None


def _skip_leading_inert(sql: str, idx: int) -> int:
    """Advance ``idx`` past leading whitespace and inert spans (finding F3).

    Returns the index of the first REAL (non-whitespace, non-inert) character
    at/after ``idx``, skipping whitespace and any string-literal / SQL-comment
    spans via the shared :func:`_skip_inert` skipper (no third hand-rolled
    lexer). Used to move the scope-injection ``after`` anchor PAST a comment that
    immediately follows the ``WHERE`` / ``FROM`` keyword (e.g. ``WHERE -- c\\n a =
    :a`` or ``WHERE /* c */ a = :a``). Without this, the tail search treats that
    leading comment as the WHERE clause's tail boundary and produces malformed
    ``WHERE AND <pred>`` SQL (the comment, not the predicate, becomes the tail).
    Capped at ``len(sql)`` so the result is always a valid slice index.
    """
    n = len(sql)
    i = idx
    while i < n:
        if sql[i].isspace():
            i += 1
            continue
        skipped = _skip_inert(sql, i)
        if skipped is not None:
            i = skipped
            continue
        break
    return i


def _depth0_where_position(sql: str) -> int:
    """Return the index just past the first depth-0 ``WHERE`` keyword, or 0.

    Used to anchor the scope-injection tail search so a comment that appears
    BEFORE the depth-0 WHERE is not mistaken for the trailing tail (finding A2).
    """
    for kw, depth, start in _iter_sql_tokens(sql):
        if depth == 0 and kw == "WHERE":
            return start + len("WHERE")
    return 0


def _depth0_from_target_end(sql: str) -> int:
    """Return the index just past the depth-0 ``FROM`` keyword, or 0.

    Anchors the no-WHERE scope-injection tail search so a comment in the
    projection list (before the FROM) is not mistaken for the tail (finding A2).
    """
    for kw, depth, start in _iter_sql_tokens(sql):
        if depth == 0 and kw == "FROM":
            return start + len("FROM")
    return 0


def _depth0_tail_position(sql: str, after: int = 0) -> int:
    """Return the index of the first depth-0 trailing clause keyword, or ``len``.

    The scope predicate must be inserted BEFORE a depth-0 GROUP BY / ORDER BY /
    LIMIT / etc. tail so it lands inside the WHERE clause -- but a tail keyword
    INSIDE a subquery (depth > 0) must be ignored (it is not the outer query's
    tail). Depth-aware so an ORDER BY inside an IN-subquery does not split the
    injection point (finding #6 robustness). A trailing depth-0 comment AT/AFTER
    ``after`` is ALSO a boundary so the injected predicate never lands after a
    ``--`` (finding A2); ``after`` excludes a comment that precedes the WHERE /
    FROM anchor from being treated as the tail.
    """
    boundary = len(sql)
    for kw, depth, start in _iter_sql_tokens(sql):
        if depth == 0 and kw in _POST_WHERE_KEYWORDS and start >= after:
            boundary = start
            break
    comment_at = _first_depth0_comment(sql, after=after)
    if comment_at is not None and comment_at < boundary:
        boundary = comment_at
    return boundary


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
        bounded compiler: its ``on`` column cannot be batched into an ``IN`` list
        (opaque child SQL), or its trailing ``ORDER BY`` / ``LIMIT`` cannot be
        expressed in the batched form (finding #4) -- a per-parent ``LIMIT``
        without ``ORDER BY`` (nondeterministic top-N), an ``OFFSET`` (no
        per-parent offset in the IN-list form), or a per-parent ``LIMIT`` on a
        child that ALSO has its own nested grandchildren (ambiguous window
        partition + further batching). A scoped nested child whose SQL already
        carries an author-written predicate on the scope column fails loud with
        the parent path's "ambiguous scope ownership" message (finding R3-3): the
        compiler owns the tenant-scope guarantee, and the child's residual
        re-parenthesization would otherwise hide the conflict from the runtime
        depth-0 conflict check.

        Snapshot-safe: reads only the frozen ``_ShapeMeta`` sidecars and does
        pure string analysis -- no database access -- so the ``shapecheck``
        contract can call it at ``app.check()`` time on every used Shape and
        convert :class:`ShapeError` into a contract issue (finding #3).
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
            # Scope-ownership parity with the parent path (finding R3-3): the
            # parent fails loud when the author wrote their OWN predicate on the
            # scope column (the compiler owns the tenant-scope guarantee). On a
            # scoped CHILD the author's depth-0 ``community_id = :other`` would be
            # re-parenthesized into the IN-list residual (depth 1) before runtime
            # injection, so the depth-0 conflict check would miss it and silently
            # add ``AND community_id = :scope`` alongside. Run the same injection
            # on the child's ORIGINAL SQL here -- _inject_scope raises the same
            # "ambiguous scope ownership" ShapeError for an author predicate, and
            # is a harmless idempotent check for a clean scoped child.
            if child_meta.scope is not None:
                _inject_scope(child_meta.sql, child_meta.scope)
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
            # ORDER BY / LIMIT expressibility in the batched IN-list form (#4)
            # and per-parent join-equality isolability (finding A3).
            decomp = _decompose_child(child_meta.sql, child.on)
            if not decomp.join_isolated:
                msg = (
                    f"Nested child {child_meta.name!r} of {meta.name!r} has a "
                    f"depth-0 WHERE whose per-parent join predicate {child.on!r} "
                    "cannot be cleanly isolated: it must appear as a simple "
                    f"'{child.on} = :param' equality conjoined with AND at the top "
                    "level of the WHERE (not OR'd, not a non-equality predicate, "
                    "and present). The bounded compiler replaces that one equality "
                    f"with 'WHERE {child.on} IN (...)' and preserves the residual "
                    "filters; an un-isolable join predicate would silently drop or "
                    f"corrupt your filters. Rewrite the {child_meta.name!r} WHERE so "
                    f"'{child.on} = :param' is a top-level AND conjunct."
                )
                raise ShapeError(msg)
            if decomp.has_offset:
                msg = (
                    f"Nested child {child_meta.name!r} of {meta.name!r} declares an "
                    "OFFSET, which is inexpressible in the batched per-parent "
                    "IN-list form (OFFSET would apply globally, not per parent). "
                    "Remove the OFFSET from the child SQL."
                )
                raise ShapeError(msg)
            if decomp.limit is not None and decomp.order_by is None:
                msg = (
                    f"Nested child {child_meta.name!r} of {meta.name!r} declares a "
                    "per-parent LIMIT with no ORDER BY. The batched per-parent "
                    "top-N rewrite (ROW_NUMBER() OVER (PARTITION BY ... ORDER BY "
                    "...)) requires a deterministic ordering. Add an ORDER BY to "
                    "the child SQL (or remove the LIMIT)."
                )
                raise ShapeError(msg)
            if decomp.limit is not None and child_meta.nested:
                msg = (
                    f"Nested child {child_meta.name!r} of {meta.name!r} declares a "
                    "per-parent LIMIT AND its own nested grandchildren. Combining "
                    "the window-partition top-N with further IN-list batching of "
                    "grandchildren is ambiguous and unsupported. Remove the LIMIT "
                    f"from {child_meta.name!r}, or flatten the grandchildren."
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


@dataclasses.dataclass(frozen=True, slots=True)
class _ChildDecomposition:
    """The structural pieces of a child SQL needed to batch it (findings #4/A3).

    Attributes:
        head: ``SELECT ... FROM <target>`` up to (excluding) the child's own
            per-parent WHERE -- the declared per-parent join equality is
            supplanted by the batched ``IN``-list, so only THAT predicate is
            dropped (the residual WHERE filters are preserved, finding A3).
        order_by: The trailing ``ORDER BY ...`` clause text (without the keyword),
            or ``None``. Re-attached after the ``IN``-list (no LIMIT) or used as
            the window ``PARTITION BY ... ORDER BY`` ordering (per-parent LIMIT).
        limit: The per-parent ``LIMIT`` value as declared (an int literal or a
            ``:name`` placeholder token), or ``None``.
        has_offset: ``True`` when the child declared an ``OFFSET`` -- batched
            per-parent OFFSET is inexpressible, so it fails loud at decoration.
        residual_where: The child's depth-0 WHERE predicates with the per-parent
            join equality (``{on} = :param``) removed, or ``None`` when the WHERE
            was nothing but the join predicate. Re-combined as
            ``WHERE {on} IN (...) AND (<residual>)`` so author filters such as
            ``deleted = 0`` survive the IN-list rewrite (finding A3).
        join_isolated: ``True`` when the per-parent join equality was cleanly
            isolated from the depth-0 WHERE (a top-level ``AND`` conjunct that is
            a simple ``{on} = :placeholder`` equality). ``False`` when there is a
            depth-0 WHERE but the join predicate is OR'd at top level, is not a
            simple equality, or is absent -- :meth:`Shape.validate` fails loud
            rather than the compiler silently dropping the author's filters.
            ``True`` when the child has no depth-0 WHERE at all (nothing to drop).
    """

    head: str
    order_by: str | None
    limit: str | None
    has_offset: bool
    residual_where: str | None
    join_isolated: bool


def _split_top_level_and(where_body: str) -> tuple[list[str], bool] | None:
    """Split a WHERE body into its top-level ``AND`` conjuncts.

    Returns ``(conjuncts, ok)`` where ``conjuncts`` is the list of top-level
    predicate texts (split on depth-0 ``AND`` within the WHERE body) and ``ok``
    is ``False`` when a top-level ``OR`` is present (removing one conjunct from a
    disjunction is unsound, so the join predicate cannot be safely isolated --
    finding A3). Returns ``None`` when the body is empty. Inert-span aware so an
    ``AND``/``OR`` inside a string, comment, or sub-paren is not a split point.
    """
    if not where_body.strip():
        return None
    conjuncts: list[str] = []
    has_top_level_or = False
    last = 0
    for kw, depth, start in _iter_sql_tokens(where_body):
        if depth != 0:
            continue
        if kw == "OR":
            has_top_level_or = True
        elif kw == "AND":
            conjuncts.append(where_body[last:start].strip())
            last = start + len("AND")
    conjuncts.append(where_body[last:].strip())
    conjuncts = [c for c in conjuncts if c]
    return conjuncts, not has_top_level_or


# A simple per-parent join equality predicate: ``{on} = :placeholder`` with an
# optional table qualifier (``t.{on}``). Anchored both edges (finding A1) so a
# column whose suffix equals ``on`` is not a false match.
def _is_join_equality(conjunct: str, on: str) -> bool:
    """Return whether ``conjunct`` is a simple ``{on} = :placeholder`` equality."""
    pattern = re.compile(
        rf"^\s*(?<![\w.])(?:\w+\.)?{re.escape(on)}(?![\w])\s*=\s*:[A-Za-z_]\w*\s*$",
        re.IGNORECASE,
    )
    return pattern.match(conjunct) is not None


def _decompose_child(sql: str, on: str) -> _ChildDecomposition:
    """Decompose a child SQL into head + residual WHERE + ORDER BY / LIMIT.

    The bounded compiler replaces the child's per-parent join EQUALITY with a
    single batched ``WHERE {on} IN (...)``, so ONLY that equality is dropped --
    the residual WHERE filters (e.g. ``deleted = 0``) are PRESERVED and
    recombined as ``WHERE {on} IN (...) AND (<residual>)`` (finding A3). The
    trailing ``ORDER BY`` and ``LIMIT`` are also preserved (finding #4: the old
    ``_child_head`` silently discarded them, turning "top 5 recent comments per
    card" into "all comments, arbitrary order"). All clause boundaries are found
    at paren depth 0 so an ORDER BY / LIMIT / AND inside a subquery is left
    attached. The ``on`` argument is the child column joining back to the parent
    key; it is used to locate (and drop) the per-parent join equality.
    """
    where_at: int | None = None
    order_at: int | None = None
    limit_at: int | None = None
    offset_at: int | None = None
    for kw, depth, start in _iter_sql_tokens(sql):
        if depth != 0:
            continue
        if kw == "WHERE" and where_at is None:
            where_at = start
        elif kw == "ORDER" and order_at is None:
            order_at = start
        elif kw == "LIMIT" and limit_at is None:
            limit_at = start
        elif kw == "OFFSET" and offset_at is None:
            offset_at = start

    # Head = everything before the first depth-0 clause boundary (WHERE / ORDER /
    # LIMIT / OFFSET, whichever comes first).
    boundaries = [p for p in (where_at, order_at, limit_at, offset_at) if p is not None]
    head_end = min(boundaries) if boundaries else len(sql)
    head = sql[:head_end].rstrip()

    # Depth-0 WHERE body = text from after WHERE up to the next depth-0 clause
    # boundary (ORDER / LIMIT / OFFSET) -- the per-parent join equality is dropped
    # and the residual conjuncts are preserved (finding A3).
    residual_where: str | None = None
    join_isolated = True  # no WHERE at all -> nothing to isolate -> vacuously ok
    if where_at is not None:
        where_end_candidates = [
            p for p in (order_at, limit_at, offset_at) if p is not None and p > where_at
        ]
        where_end = min(where_end_candidates) if where_end_candidates else len(sql)
        where_body = sql[where_at + len("WHERE") : where_end].strip()
        split = _split_top_level_and(where_body)
        join_isolated = False
        if split is not None:
            conjuncts, no_top_level_or = split
            if no_top_level_or:
                join_idx = next(
                    (i for i, c in enumerate(conjuncts) if _is_join_equality(c, on)), None
                )
                if join_idx is not None:
                    join_isolated = True
                    residual = [c for i, c in enumerate(conjuncts) if i != join_idx]
                    residual_where = " AND ".join(residual) if residual else None

    # ORDER BY clause text (without the keyword), bounded by LIMIT / OFFSET.
    order_by: str | None = None
    if order_at is not None:
        order_end_candidates = [p for p in (limit_at, offset_at) if p is not None and p > order_at]
        order_end = min(order_end_candidates) if order_end_candidates else len(sql)
        # Strip the leading ``ORDER`` + ``BY`` keywords.
        clause = sql[order_at:order_end].strip()
        clause = re.sub(r"^ORDER\s+BY\s+", "", clause, count=1, flags=re.IGNORECASE)
        order_by = clause.strip() or None

    # LIMIT value (int literal or :name token), bounded by OFFSET.
    limit: str | None = None
    if limit_at is not None:
        limit_end_candidates = [offset_at] if offset_at is not None and offset_at > limit_at else []
        limit_end = min(limit_end_candidates) if limit_end_candidates else len(sql)
        clause = sql[limit_at:limit_end].strip()
        clause = re.sub(r"^LIMIT\s+", "", clause, count=1, flags=re.IGNORECASE)
        limit = clause.strip() or None

    return _ChildDecomposition(
        head=head,
        order_by=order_by,
        limit=limit,
        has_offset=offset_at is not None,
        residual_where=residual_where,
        join_isolated=join_isolated,
    )


def _batched_child_sql(child_meta: _ShapeMeta, on: str, key_names: Sequence[str]) -> str:
    """Build the ONE batched ``IN``-list query for a child level (findings #4/#5/A3).

    ``key_names`` is the ordered tuple of generated key placeholder names for
    THIS chunk (``__chirp_k0``, ``__chirp_k1``, ...). The generated batch-key
    names use the reserved ``__chirp_`` prefix (matching ``__chirp_rn``) so they
    can never collide with an author placeholder that happens to be named ``k0``
    -- a collision would silently bind the author's residual filter to a
    parent-key value (finding R3-2). The child's per-parent join EQUALITY is
    replaced by a single ``WHERE {on} IN (...)``, and the child's RESIDUAL WHERE
    filters (e.g. ``deleted = 0``) are preserved as ``AND (<residual>)`` so the
    author's row exclusions survive the IN-list rewrite (finding A3). The child's
    declared trailing ``ORDER BY`` is re-attached and a per-parent ``LIMIT`` is
    rewritten into a ``ROW_NUMBER() OVER (PARTITION BY {on} ORDER BY ...)`` window
    top-N (so each parent's children are limited independently rather than
    globally); the OUTER select orders on the PROJECTED ``{on}, __chirp_rn`` so
    within-parent order is deterministic and not driver-dependent without
    referencing a column the inner derived table does not expose (findings
    A4/R3-1). When the child declares ``scope=``, the scope predicate is
    structurally injected into the inner query too (every child statement
    scoped).

    Inexpressible cases (LIMIT without ORDER BY, OFFSET, per-parent LIMIT with
    further nested grandchildren, an un-isolable join predicate) are rejected at
    decoration by :meth:`Shape.validate`, not here.
    """
    decomp = _decompose_child(child_meta.sql, on)
    placeholders = ", ".join(f":{kn}" for kn in key_names)
    in_list = f"WHERE {on} IN ({placeholders})"
    if decomp.residual_where is not None:
        # Preserve the author's residual WHERE filters (finding A3): the IN-list
        # replaces ONLY the per-parent join equality; everything else still
        # filters the child rows. Parenthesized so a residual OR binds correctly
        # against the IN-list AND.
        in_list = f"{in_list} AND ({decomp.residual_where})"

    if decomp.limit is None:
        # No per-parent LIMIT: re-attach ORDER BY after the IN-list (after any
        # injected scope predicate so the predicate lands in the WHERE).
        sql = f"{decomp.head} {in_list}"
        if child_meta.scope is not None:
            sql = _inject_scope(sql, child_meta.scope)
        if decomp.order_by is not None:
            sql = f"{sql} ORDER BY {decomp.order_by}"
        return sql

    # Per-parent LIMIT -> window-function top-N. The inner SELECT keeps the
    # child's projection (head) + ROW_NUMBER() partitioned by the join column;
    # the outer SELECT filters to the per-parent top-N. ``__chirp_rn`` is not a
    # child dataclass field, so map_row drops it (rules_data_shapes documents
    # extra columns are dropped). ``:limit`` flows through the shared scanner so
    # _placeholder_names / _member_params can thread it.
    inner = f"{decomp.head} {in_list}"
    if child_meta.scope is not None:
        inner = _inject_scope(inner, child_meta.scope)
    # Splice ROW_NUMBER() into the inner projection: ``SELECT <cols>`` ->
    # ``SELECT <cols>, ROW_NUMBER() OVER (...) AS __chirp_rn``. We add it after
    # the projection by inserting before the first depth-0 FROM.
    window = f"ROW_NUMBER() OVER (PARTITION BY {on} ORDER BY {decomp.order_by}) AS __chirp_rn"
    inner = _splice_window_column(inner, window)
    # Re-establish a deterministic OUTER order (finding A4 + R3-1): SQL does not
    # guarantee an inner ORDER BY propagates through a derived table (PostgreSQL
    # warns against relying on it), so within-parent child order would otherwise
    # be driver-dependent. The within-parent order is ALREADY encoded by the
    # inner ``ROW_NUMBER() OVER (PARTITION BY {on} ORDER BY {order_by})`` as
    # ``__chirp_rn``, so the outer query orders on PROJECTED columns only --
    # ``{on}`` (always projected: the join column is a required child field) then
    # ``__chirp_rn`` (projected by the inner). Re-emitting ``decomp.order_by`` on
    # the outer query would reference a column the inner derived table does not
    # expose when the child's ORDER BY uses a non-projected column (the canonical
    # ``ORDER BY created_at DESC LIMIT N`` where ``created_at`` is not SELECTed)
    # -> "no such column" crash. Ordering on ``__chirp_rn`` reproduces the
    # within-parent ORDER BY exactly because rank 1 is the first row in that order.
    return f"SELECT * FROM ({inner}) WHERE __chirp_rn <= {decomp.limit} ORDER BY {on}, __chirp_rn"


def _splice_window_column(inner: str, window: str) -> str:
    """Insert ``, {window}`` into the projection of ``inner`` before its FROM.

    Locates the first depth-0 ``FROM`` and inserts the window column at the end
    of the projection list. Used by the per-parent-LIMIT top-N rewrite (#4).
    """
    for kw, depth, start in _iter_sql_tokens(inner):
        if depth == 0 and kw == "FROM":
            projection = inner[:start].rstrip()
            rest = inner[start:]
            return f"{projection}, {window} {rest}"
    # Unreachable: _scope_injectable guarantees a FROM, but guard defensively.
    return inner  # pragma: no cover


async def _resolve_children(
    parents: list[Any],
    child: NestedShape,
    db: Database,
    params: Mapping[str, Any],
) -> list[Any]:
    """Run the batched ``IN``-list query(ies) for ``child`` and attach to parents.

    Collects the distinct parent ``key`` values, runs ONE query per chunk of
    ``_MAX_IN_LIST_KEYS`` keys (finding #5: a single IN-list with one placeholder
    per key crashes at ~32k keys with "too many SQL variables"), merges the
    chunk results, groups child rows by their ``on`` value, recurses into the
    child's own nested children, and rebuilds each parent via
    :func:`dataclasses.replace` (frozen-safe).

    Returns the list of parents with the nested field populated. Query count for
    this level is ``ceil(distinct_keys / _MAX_IN_LIST_KEYS)`` -- O(chunks), still
    independent of the child ROW count (the #167 bounded-query guarantee).
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

    # Chunk the parent keys so the IN-list never exceeds the driver's bind-var
    # ceiling. Read the module constant at call time (never a default arg) so a
    # test can monkeypatch chirp.data.shapes._MAX_IN_LIST_KEYS.
    chunk_size = _MAX_IN_LIST_KEYS
    child_rows: list[Any] = []
    for start in range(0, len(key_values), chunk_size):
        chunk = key_values[start : start + chunk_size]
        # Generated batch-key placeholders use the reserved ``__chirp_`` prefix
        # (matching ``__chirp_rn``) so they can NEVER collide with an author
        # placeholder named ``k0``/``k1``/... in the child's residual WHERE --
        # a collision would seed the author's filter with a parent-key value
        # instead of threading the author's own param (finding R3-2).
        key_names = tuple(f"__chirp_k{i}" for i in range(len(chunk)))
        sql_template = _batched_child_sql(child_meta, child.on, key_names)
        child_params: dict[str, Any] = dict(zip(key_names, chunk, strict=True))
        # Thread the tenant scope value through to the child IN-list query.
        if child_meta.scope is not None and "scope" in params:
            child_params["scope"] = params["scope"]
        # Thread a per-parent LIMIT placeholder when the child SQL declared one.
        for pname in _placeholder_names(sql_template):
            if pname not in child_params and pname in params:
                child_params[pname] = params[pname]
        sql, ordered = _bind_params(sql_template, db._driver, child_params)
        child_rows.extend(await db.fetch(child.cls, sql, *ordered))

    # Recurse: a grandchild level is still bounded (over ALL merged child rows).
    if child_meta.nested:
        for grandchild in child_meta.nested:
            child_rows = await _resolve_children(child_rows, grandchild, db, params)

    # Group children by their ``on`` value (over the merged chunk results).
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
    """Bounded nested loader: 1 parent query + batched query(ies) per child level.

    Runs the parent SELECT (scope-injected when declared), then for EACH declared
    child level runs ONE batched ``IN``-list query per chunk of
    ``_MAX_IN_LIST_KEYS`` distinct parent keys (never per parent ROW). Query
    count = ``1 + sum(ceil(distinct_keys_at_level / _MAX_IN_LIST_KEYS))`` --
    bounded, ``O(depth * chunks)``, independent of the parent ROW count ``N``
    (the #167 no-N+1 guarantee; chunking added for finding #5 so the IN-list
    never exceeds the driver's bind-variable ceiling).
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

    A thin consumer of the shared :func:`_scan_placeholders` scanner (which is
    ``::cast``- and quoted-string-aware), so the coalescer asks for exactly the
    params each member statement binds and never drifts from :func:`_bind_params`
    (finding #8).
    """
    return {name for name, _, _ in _scan_placeholders(sql)}
