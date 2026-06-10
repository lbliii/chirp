"""Typed-SQL column-mapping contract (SQL in, frozen dataclasses out).

Chirp's data layer maps SQL rows onto frozen dataclasses via
``db.fetch(cls, sql)`` / ``db.fetch_one(cls, sql)`` / ``db.stream(cls, sql)``
(:mod:`chirp.data._mapping`). A column SELECTed by the SQL that exists on
*neither* the target dataclass *nor* the declared table schema is drift: the
query runs, the column is silently ignored by ``map_row`` (extra columns are
dropped), and the bug only surfaces when the row is missing data at runtime.

This rule promotes that drift to an ``app.check()`` ``ERROR`` *when it is
statically analyzable*. It is deliberately conservative -- it does not become an
ORM, a model registry, or a SQL engine. It only fires when all of the following
can be resolved from static handler source:

* a literal first positional ``cls`` argument that names a frozen dataclass
  reachable in the handler's module globals, and
* a string-literal SQL with an explicit ``SELECT col, col, ...`` list
  (``SELECT *``, expressions, joins with ambiguous columns, and dynamic SQL are
  skipped -- no false positives).

A SELECTed column is flagged only when it is absent from the dataclass fields
**and** (when a declared schema is available) absent from every table column in
that schema. That double-guard keeps the check quiet for column aliases the
schema cannot see and for db-less / schema-less apps, honoring the data
steward's "data stays optional" rule and the contracts steward's "no noisy
warnings" rule.

Severity is ``ERROR`` and overridable via
``app.override_contract_severity("data", Severity.ERROR/WARNING/INFO)``.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
import re
from typing import TYPE_CHECKING, Any

from .types import ContractIssue, Severity

if TYPE_CHECKING:
    from chirp.data.schema.types import SchemaSnapshot

# The fetch-family methods that take ``(cls, sql, *params)`` and map rows
# through a frozen dataclass. ``fetch_val`` / ``fetch_raw`` / ``execute`` are
# intentionally excluded -- they do not map onto a dataclass.
_FETCH_METHODS = frozenset({"fetch", "fetch_one", "stream"})

# Receiver names we treat as a chirp.data ``Database`` handle. The fetch-family
# method names are generic enough to collide with unrelated APIs (an LLM
# client's ``.stream()``, a query builder's ``.fetch()``), so we only analyze
# calls whose receiver is idiomatically the database: a bare ``db`` / ``database``
# name (or ``*_db``), an attribute ending in those (``self.db``, ``app.db``,
# ``g.db``), or a ``get_db()`` call. This trades a few false negatives (a db
# handle bound to an unconventional name) for zero false-positive ERRORs on
# unrelated objects -- the rule's core promise of no noisy warnings.
_DB_RECEIVER_NAMES = frozenset({"db", "database"})

# Extract the SELECT column list from a single-table-ish query. Group 1 is the
# raw projection between SELECT and FROM. We only trust this when the projection
# is a simple comma-separated identifier list (handled in _parse_select_columns).
_SELECT_RE = re.compile(r"\bSELECT\b\s+(.*?)\s+\bFROM\b", re.IGNORECASE | re.DOTALL)

# A trailing ``AS alias`` projection element. We map the *output* name (what
# map_row sees) -- the alias when present, else the column.
_ALIAS_RE = re.compile(r"\bAS\s+(\w+)\s*$", re.IGNORECASE)


def _strip_sql_comments(sql: str) -> str:
    """Return ``sql`` with SQL comments replaced by a single space, string-aware.

    ``_parse_select_columns`` is the single-source-of-truth SELECT parser (also
    consumed by codegen and the data contract, and -- via ``shapes._scope_injectable``
    -- the tenant-scope injectability gate). A comment in the PROJECTION list
    (``SELECT id /* note */, name FROM t`` or ``SELECT id -- c\\nFROM t``) is NOT
    opaque SQL, but a naive regex parse choked on it and returned ``None`` --
    surfacing a misleading "CTE / UNION / SELECT * / derived-table" rejection for
    what is really just a comment. We strip comments first so a commented column
    list still parses.

    Comment forms (mirroring the SQL standard): line comments ``-- ... EOL`` and
    block comments ``/* ... */`` (non-nesting). Each is replaced by a single
    space (never deleted) so adjacent tokens cannot merge (``a/**/b`` must not
    become ``ab``). The scan is **string-literal aware**: a ``--`` / ``/*`` inside
    a ``'...'`` or ``"..."`` literal (honoring doubled-quote ``''`` / ``""``
    escapes) is NOT a comment and is preserved verbatim, so a quoted identifier or
    string body is never corrupted. A line comment's terminating newline is
    preserved (kept outside the replacement) so line structure is unchanged.
    """
    out: list[str] = []
    i = 0
    n = len(sql)
    while i < n:
        ch = sql[i]
        # String literal: copy its body verbatim, honoring doubled-quote escapes.
        if ch == "'" or ch == '"':
            quote = ch
            out.append(ch)
            j = i + 1
            while j < n:
                out.append(sql[j])
                if sql[j] == quote:
                    if j + 1 < n and sql[j + 1] == quote:
                        out.append(sql[j + 1])  # doubled-quote escape, stay inside
                        j += 2
                        continue
                    j += 1
                    break
                j += 1
            i = j
            continue
        # Line comment: ``-- ... EOL`` -> single space (newline preserved).
        if ch == "-" and i + 1 < n and sql[i + 1] == "-":
            j = i + 2
            while j < n and sql[j] != "\n":
                j += 1
            out.append(" ")
            i = j
            continue
        # Block comment: ``/* ... */`` (non-nesting) -> single space.
        if ch == "/" and i + 1 < n and sql[i + 1] == "*":
            j = i + 2
            while j < n and not (sql[j] == "*" and j + 1 < n and sql[j + 1] == "/"):
                j += 1
            out.append(" ")
            # Skip the closing ``*/`` when present; an unterminated block comment
            # runs to end-of-string.
            i = j + 2 if j < n else n
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _split_top_level(projection: str) -> list[str]:
    """Split a projection on top-level commas (ignoring commas inside parens)."""
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for char in projection:
        if char == "(":
            depth += 1
            current.append(char)
        elif char == ")":
            depth -= 1
            current.append(char)
        elif char == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    if current:
        parts.append("".join(current))
    return parts


def _parse_select_columns(sql: str) -> tuple[str, ...] | None:
    """Return the output column names of a simple ``SELECT a, b`` query.

    Returns ``None`` (skip -- not statically analyzable) when the projection is
    ``SELECT *``, contains an expression / function call / subquery / DISTINCT,
    or the SQL has no analyzable ``SELECT ... FROM`` shape. Returns the resolved
    output names (alias-aware) otherwise.
    """
    # Strip SQL comments first (string-literal aware) so a comment in the
    # projection list does not make an otherwise-simple SELECT opaque and surface
    # a misleading "CTE / UNION / SELECT * / derived-table" rejection. All
    # downstream keyword/projection analysis then reasons over comment-free SQL.
    sql = _strip_sql_comments(sql)
    # CTEs put the first SELECT/FROM inside the CTE body, and compound queries
    # (UNION/INTERSECT/EXCEPT) have several projections; the single first-match
    # regex below cannot pick the right one, so skip rather than analyze the
    # wrong arm (a silent false-negative becomes an explicit, documented skip).
    if re.match(r"\s*WITH\b", sql, re.IGNORECASE):
        return None
    if re.search(r"\b(?:UNION|INTERSECT|EXCEPT)\b", sql, re.IGNORECASE):
        return None

    match = _SELECT_RE.search(sql)
    if match is None:
        return None
    projection = match.group(1).strip()
    if not projection or projection == "*":
        return None
    # Bail on DISTINCT / aggregate-heavy projections we can't reason about.
    if projection.upper().startswith("DISTINCT"):
        return None

    columns: list[str] = []
    for raw in _split_top_level(projection):
        part = raw.strip()
        if not part:
            return None
        # Star projection anywhere (``*`` or ``users.*``) -> not analyzable.
        if part == "*" or part.endswith(".*"):
            return None
        alias_match = _ALIAS_RE.search(part)
        if alias_match is not None:
            columns.append(alias_match.group(1))
            continue
        # Any expression character means this isn't a bare column reference:
        # ``(``, ``)``, arithmetic, function calls, string literals, etc.
        if not re.fullmatch(r'[\w."`]+', part):
            return None
        # Strip a table qualifier (``users.id`` -> ``id``) and quoting.
        name = part.split(".")[-1].strip('"').strip("`")
        if not name.isidentifier():
            return None
        columns.append(name)
    return tuple(columns) if columns else None


def _dataclass_fields(cls: Any) -> set[str] | None:
    """Return the field-name set for a frozen dataclass type, else ``None``."""
    if not isinstance(cls, type) or not dataclasses.is_dataclass(cls):
        return None
    return {f.name for f in dataclasses.fields(cls)}


def _resolve_cls(node: ast.expr, handler_globals: dict[str, Any]) -> Any:
    """Resolve a ``cls`` argument AST node to a runtime object, if statically known.

    Only resolves bare ``Name`` references against the handler's module globals
    (e.g. ``db.fetch(User, ...)`` where ``User`` is a module-level dataclass).
    Attribute access, subscripts, calls, and locals are not resolvable -> skip.
    """
    if isinstance(node, ast.Name):
        return handler_globals.get(node.id)
    return None


def _is_db_receiver(value: ast.expr) -> bool:
    """True when the call receiver looks like a chirp.data ``Database`` handle.

    Recognizes ``db`` / ``database`` / ``*_db`` names, attribute access ending in
    those (``self.db``, ``app.db``, ``g.db``), and ``get_db()`` calls. Anything
    else (an arbitrary object that merely exposes a ``fetch``/``stream`` method)
    is rejected so the rule never ERRORs on an unrelated API.
    """
    if isinstance(value, ast.Call):
        fn = value.func
        if isinstance(fn, ast.Name):
            return fn.id == "get_db"
        if isinstance(fn, ast.Attribute):
            return fn.attr == "get_db"
        return False
    if isinstance(value, ast.Name):
        return value.id in _DB_RECEIVER_NAMES or value.id.endswith("_db")
    if isinstance(value, ast.Attribute):
        return value.attr in _DB_RECEIVER_NAMES or value.attr.endswith("_db")
    return False


def _iter_fetch_calls(tree: ast.AST) -> list[tuple[ast.expr, str]]:
    """Yield ``(cls_node, sql_literal)`` for statically analyzable fetch calls.

    A call is analyzable when it is
    ``<db>.fetch|fetch_one|stream(CLS, "literal sql", ...)`` where ``<db>`` is an
    idiomatic chirp.data ``Database`` receiver (see :func:`_is_db_receiver`),
    with a string-literal SQL and at least the ``cls`` positional argument.
    Dynamic SQL (f-strings, concatenation, names) and calls on unrelated
    receivers are skipped.
    """
    found: list[tuple[ast.expr, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr not in _FETCH_METHODS:
            continue
        if not _is_db_receiver(func.value):
            # Not a recognizable Database receiver -- a generic .fetch/.stream on
            # an unrelated object. Skip to avoid a false-positive ERROR.
            continue
        if len(node.args) < 2:
            continue
        cls_node = node.args[0]
        sql_node = node.args[1]
        if not (isinstance(sql_node, ast.Constant) and isinstance(sql_node.value, str)):
            # Dynamic SQL -- not statically analyzable, skip silently.
            continue
        found.append((cls_node, sql_node.value))
    return found


def _schema_columns(schema: SchemaSnapshot | None) -> set[str] | None:
    """Union of all column names across all tables in the declared schema.

    Returns ``None`` when no schema is available -- the check then relies on the
    dataclass fields alone and only flags columns that match no field, which is
    still a real drift (a SELECTed column the dataclass cannot receive).
    """
    if schema is None:
        return None
    columns: set[str] = set()
    for table in schema.tables.values():
        columns.update(table.columns)
    return columns


def _dedent(src: str) -> str:
    """Normalize indentation so ``ast.parse`` accepts a nested handler source."""
    return inspect.cleandoc("\n" + src) if src and src[0] in " \t" else src


def check_data_shapes(
    router: object,
    schema: SchemaSnapshot | None,
) -> list[ContractIssue]:
    """Flag ``db.fetch(cls, sql)`` columns that map to no dataclass field.

    For each statically-resolvable fetch call on a route handler:

    * resolve ``cls`` to a frozen dataclass (skip if not resolvable),
    * parse the SELECT column list (skip ``SELECT *`` / expressions / dynamic SQL),
    * a SELECTed column absent from the dataclass fields **and** (when a schema is
      available) absent from every declared table column is real drift -> ``ERROR``.

    Returns one issue per (route, dataclass, offending column).
    """
    issues: list[ContractIssue] = []
    routes = getattr(router, "routes", None)
    if not routes:
        return issues

    schema_columns = _schema_columns(schema)
    seen: set[tuple[str, str, str]] = set()

    for route in routes:
        handler = getattr(route, "handler", None)
        page_src = getattr(route, "page_source_handler", None)
        handler_for_source = page_src if page_src is not None else handler
        if handler_for_source is None:
            continue
        try:
            src = inspect.getsource(handler_for_source)
        except TypeError, OSError:
            continue
        try:
            tree = ast.parse(_dedent(src))
        except SyntaxError:
            continue

        handler_globals = getattr(handler_for_source, "__globals__", {})
        path = getattr(route, "path", "") or ""

        for cls_node, sql in _iter_fetch_calls(tree):
            cls = _resolve_cls(cls_node, handler_globals)
            if cls is None:
                continue
            fields = _dataclass_fields(cls)
            if fields is None:
                continue
            columns = _parse_select_columns(sql)
            if columns is None:
                continue
            cls_name = getattr(cls, "__name__", str(cls))
            for column in columns:
                if column in fields:
                    continue
                # Not a field. Only flag as drift when we can also confirm the
                # column is unknown to the declared schema (or there is no schema
                # at all to receive it). When a schema IS present and the column
                # exists in some table, it's likely a legitimate column the
                # dataclass simply doesn't read -- not a typo -- so stay quiet.
                if schema_columns is not None and column in schema_columns:
                    continue
                key = (path, cls_name, column)
                if key in seen:
                    continue
                seen.add(key)
                if schema_columns is None:
                    detail = (
                        f"'{column}' is not a field on {cls_name} and no declared "
                        "schema was available to confirm it exists. Add the field "
                        "to the dataclass, fix the SELECT, or alias the column."
                    )
                else:
                    detail = (
                        f"'{column}' is not a field on {cls_name} and is not a "
                        "column in any declared table. This is almost certainly a "
                        "typo or schema drift -- the value would be silently dropped "
                        "by row mapping at runtime."
                    )
                issues.append(
                    ContractIssue(
                        severity=Severity.ERROR,
                        category="data",
                        message=(
                            f"Route '{path}' selects column '{column}' which maps to "
                            f"no field on '{cls_name}'."
                        ),
                        route=path,
                        details=detail,
                    )
                )
    return issues
