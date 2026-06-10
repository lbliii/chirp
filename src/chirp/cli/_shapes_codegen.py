"""``chirp shapes-codegen`` — suggest ``@shape`` decorators and audit drift (#172).

Two jobs, both incremental and non-destructive by design:

1. **Ingest + emit.** Scan target Python modules for frozen dataclasses sitting
   near an explicit named-column ``SELECT`` literal, pair each dataclass to the
   ``SELECT`` whose output columns are a subset of the dataclass fields, and emit
   a ``@shape("SELECT ...")`` decorator suggestion above each matched class
   (view-by-view, one suggestion per pair). ``--dry-run`` prints the unified diff
   and writes nothing.

2. **Day-one audit (``--audit``).** Load an app's ``surface_contracts`` registry
   (set via ``app.set_contract_check_data("surface_contracts", {...})``) and
   report every surface name with no backing Shape — REUSING the L2 registry-drift
   logic (:func:`chirp.contracts.rules_shapecheck._check_registry_drift`), never a
   second copy. Exit non-zero when drift is found (CI-friendly), 0 otherwise.

The SELECT parsing reuses :func:`chirp.contracts.rules_data_shapes._parse_select_columns`
(the single conservative SELECT parser); ingest only pairs a class to a SELECT
the parser can read (``SELECT *`` / expressions / CTE / UNION are skipped), so the
emit step never suggests a decorator it cannot verify.

This command is intentionally best-effort and never overwrites source unless
explicitly asked: the default is a dry-run-style preview. Mirrors
``_makemigrations.py`` — lazy imports live inside :func:`run_shapes_codegen`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import argparse
    import ast
    from collections.abc import Callable
    from pathlib import Path


def run_shapes_codegen(args: argparse.Namespace) -> None:
    """Suggest ``@shape`` decorators and/or audit surface-contract drift.

    Resolves the requested mode from ``args``:

    * ``--audit`` loads the app at ``args.path`` and reports surface-contract
      names with no backing Shape; exits non-zero on drift, 0 when clean.
    * otherwise (the default) scans ``args.path`` for frozen dataclasses paired
      with a nearby explicit-column ``SELECT`` and prints a ``@shape(...)``
      suggestion above each match (``--dry-run`` is the safe default — nothing is
      written).
    """
    if getattr(args, "audit", False):
        raise SystemExit(_run_audit(args))

    _run_ingest(args)


# ---------------------------------------------------------------------------
# Audit (--audit) — REUSE the L2 registry-drift logic, do not duplicate.
# ---------------------------------------------------------------------------


def _run_audit(args: argparse.Namespace) -> int:
    """Report surface-contract names with no backing Shape; return the exit code.

    Loads the app at ``args.path`` (an import string, e.g. ``myapp:app``), reads
    its ``surface_contracts`` contract-check data, and reuses the L2
    :func:`~chirp.contracts.rules_shapecheck._check_registry_drift` against the
    live :func:`~chirp.data.shape_registry`. Returns ``1`` when any drift is found
    (so CI fails), ``0`` when clean. The drift detection — including the
    closest-match suggestion — is exactly what ``app.check()`` runs; the audit is
    a focused, exit-coded view of the same logic.
    """
    import sys

    from chirp.cli._resolve import resolve_app
    from chirp.contracts.rules_shapecheck import _check_registry_drift
    from chirp.data import shape_registry

    try:
        app = resolve_app(args.path)
    except (ModuleNotFoundError, AttributeError, TypeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    surface_contracts = _app_surface_contracts(app)
    if not surface_contracts:
        print("No surface_contracts registered — nothing to audit.")
        return 0

    registry = shape_registry()
    issues = _check_registry_drift(surface_contracts, registry)
    if not issues:
        print(f"OK — {len(surface_contracts)} surface contract(s), no Shape drift.")
        return 0

    print(f"Shape drift: {len(issues)} surface contract(s) name no registered Shape.")
    for issue in issues:
        print(f"  {issue.message}")
        if issue.details:
            print(f"    {issue.details}")
    return 1


def _app_surface_contracts(app: object) -> dict[str, str]:
    """Return the app's ``surface_contracts`` contract-check data (or ``{}``).

    The data is stored via ``app.set_contract_check_data("surface_contracts",
    {...})``; it lives on the app's mutable state. Only ``str -> str`` entries are
    kept (the same shape the drift checker consumes), so a malformed registry
    never crashes the audit.
    """
    state = getattr(app, "_mutable_state", None)
    data = getattr(state, "contract_check_data", None)
    if not isinstance(data, dict):
        return {}
    raw = data.get("surface_contracts", {})
    if not isinstance(raw, dict):
        return {}
    return {k: v for k, v in raw.items() if isinstance(k, str) and isinstance(v, str)}


# ---------------------------------------------------------------------------
# Ingest + emit (default mode) — pair dataclasses to nearby SELECT literals.
# ---------------------------------------------------------------------------


def _run_ingest(args: argparse.Namespace) -> None:
    """Scan ``args.path`` for dataclass/SELECT pairs and print ``@shape`` suggestions.

    ``--dry-run`` is the safe, write-nothing default (the only behavior in v1):
    every match prints a unified-diff-style preview of the ``@shape("SELECT ...")``
    line that would be inserted above the dataclass. Nothing on disk is modified.
    """
    from pathlib import Path

    root = Path(getattr(args, "path", None) or ".")
    files = _python_files(root)
    if not files:
        print(f"No Python files found under {root}.")
        return

    total = 0
    for path in files:
        try:
            source = path.read_text(encoding="utf-8")
        except OSError, UnicodeDecodeError:
            continue
        for suggestion in _suggest_shapes(source):
            total += 1
            print(_format_suggestion(path, suggestion))

    if total == 0:
        print("No unannotated dataclass/SELECT pairs found.")
        return

    print(f"{total} @shape suggestion(s) (dry-run — no files written).")


def _python_files(root: Path) -> list[Path]:
    """Return the ``.py`` files under ``root`` (or ``root`` itself if it is one).

    Skips dunder/cache and common virtual-env / build directories so a broad
    ``shapes-codegen .`` does not walk the whole environment.
    """
    if root.is_file():
        return [root] if root.suffix == ".py" else []
    if not root.is_dir():
        return []
    skip = {".git", "__pycache__", ".venv", "venv", "node_modules", ".mypy_cache", ".ruff_cache"}
    files: list[Path] = []
    for candidate in sorted(root.rglob("*.py")):
        if any(part in skip for part in candidate.parts):
            continue
        files.append(candidate)
    return files


def _suggest_shapes(source: str) -> list[_Suggestion]:
    """Pair frozen dataclasses to nearby explicit-column SELECTs; yield suggestions.

    Returns a list of ``_Suggestion`` (class name, line number, the chosen SELECT,
    and the SELECT's parsed columns) for every frozen dataclass that:

    * is NOT already ``@shape``-decorated (incremental — skip done work), and
    * sits near an explicit named-column ``SELECT`` literal (string constant /
      assignment in the module) whose parsed output columns are a SUBSET of the
      dataclass fields.

    A dataclass with no matching SELECT yields nothing (best-effort, view-by-view).
    """
    import ast

    from chirp.contracts.rules_data_shapes import _parse_select_columns

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    selects = _collect_select_literals(tree, _parse_select_columns)
    if not selects:
        return []

    suggestions: list[_Suggestion] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        if not _is_frozen_dataclass(node):
            continue
        if _already_shape(node):
            continue
        fields = _class_field_names(node)
        if not fields:
            continue
        match = _best_select(fields, selects)
        if match is None:
            continue
        sql, columns = match
        suggestions.append(
            _Suggestion(
                class_name=node.name,
                lineno=node.lineno,
                sql=sql,
                columns=columns,
            )
        )
    return suggestions


def _collect_select_literals(
    tree: ast.Module,
    parse_columns: Callable[[str], tuple[str, ...] | None],
) -> list[tuple[str, tuple[str, ...]]]:
    """Collect ``(sql, columns)`` for every explicit-column SELECT string in the module.

    Walks string constants (assignments and bare expressions) and keeps only those
    the conservative SELECT parser can read — ``SELECT *`` / expressions / CTE /
    UNION return ``None`` and are skipped, so a suggested ``@shape`` is always one
    ``shapecheck`` can later verify.
    """
    import ast

    out: list[tuple[str, tuple[str, ...]]] = []
    seen: set[str] = set()
    for node in ast.walk(tree):
        value = None
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            value = node.value.value
        elif isinstance(node, ast.Constant):
            value = node.value
        if not isinstance(value, str):
            continue
        text = value.strip()
        if "select" not in text.lower():
            continue
        if text in seen:
            continue
        columns = parse_columns(text)
        if not columns:
            continue
        seen.add(text)
        out.append((text, tuple(columns)))
    return out


def _best_select(
    fields: frozenset[str],
    selects: list[tuple[str, tuple[str, ...]]],
) -> tuple[str, tuple[str, ...]] | None:
    """Return the ``(sql, columns)`` whose columns best subset ``fields``, else ``None``.

    A candidate qualifies only when EVERY parsed output column is a field of the
    dataclass (columns ⊆ fields) — the pairing the blueprint specifies. Among
    qualifying candidates, the one covering the most fields wins (the richest
    verified projection), ties broken by the SQL text for determinism.
    """
    best = None
    best_cover = -1
    for sql, columns in selects:
        if not set(columns).issubset(fields):
            continue
        cover = len(columns)
        if cover > best_cover or (cover == best_cover and best is not None and sql < best[0]):
            best = (sql, columns)
            best_cover = cover
    return best


def _is_frozen_dataclass(node: ast.ClassDef) -> bool:
    """True when a ``ClassDef`` carries ``@dataclass(frozen=True)``."""
    import ast

    for deco in node.decorator_list:
        target = deco.func if isinstance(deco, ast.Call) else deco
        name = None
        if isinstance(target, ast.Name):
            name = target.id
        elif isinstance(target, ast.Attribute):
            name = target.attr
        if name != "dataclass":
            continue
        if not isinstance(deco, ast.Call):
            # Bare @dataclass is not frozen.
            continue
        for kw in deco.keywords:
            if kw.arg == "frozen" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                return True
    return False


def _already_shape(node: ast.ClassDef) -> bool:
    """True when a ``ClassDef`` already carries an ``@shape(...)`` decorator (skip it)."""
    import ast

    for deco in node.decorator_list:
        target = deco.func if isinstance(deco, ast.Call) else deco
        if isinstance(target, ast.Name) and target.id == "shape":
            return True
        if isinstance(target, ast.Attribute) and target.attr == "shape":
            return True
    return False


def _class_field_names(node: ast.ClassDef) -> frozenset[str]:
    """Return the annotated field names declared on a dataclass ``ClassDef``."""
    import ast

    names: set[str] = set()
    for stmt in node.body:
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            names.add(stmt.target.id)
    return frozenset(names)


def _format_suggestion(path: Path, suggestion: _Suggestion) -> str:
    """Render one suggestion as a unified-diff-style ``@shape`` insertion preview."""
    sql = suggestion.sql
    cls = suggestion.class_name
    lineno = suggestion.lineno
    cols = ", ".join(suggestion.columns)
    lines = [
        f"--- {path}:{lineno} ({cls})",
        f"+ @shape({sql!r})",
        "  @dataclass(frozen=True, slots=True)",
        f"  class {cls}:  # columns: {cols}",
    ]
    return "\n".join(lines)


# A lightweight value object for an ingest match — a frozen slots dataclass (the
# chirp idiom for immutable carriers).
@dataclass(frozen=True, slots=True)
class _Suggestion:
    """One dataclass/SELECT pairing the ingest step would annotate with ``@shape``."""

    class_name: str
    lineno: int
    sql: str
    columns: tuple[str, ...]
