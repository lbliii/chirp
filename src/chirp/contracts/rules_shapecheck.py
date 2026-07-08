"""Verified-Shape render contract (``shapecheck``).

The :mod:`~chirp.contracts.rules_data_shapes` ``data`` contract verifies the
*query* side: a SELECTed column that maps to no field on the ``db.fetch(cls,
sql)`` dataclass is drift. ``shapecheck`` verifies the *render* side of a
``@shape``-decorated row model (:mod:`chirp.data.shapes`): the fields a template
block reads must be fields the bound Shape actually fetched (SELECT columns) or
declared (``computed=``), and a surface-contract registry name must resolve to a
real registered Shape.

It owns four statically-decidable claims:

* **Registry drift (#166, ERROR — the marquee).** A surface-contract name whose
  target resolves to no registered Shape is a typo / a renamed-away view. This is
  fully static (registry-name -> backing-class resolution), zero false-positive,
  and the highest-value check. It runs even with no contract data registered, via
  the auto :func:`chirp.data.shape_registry`.
* **Under-fetch (#173, ERROR).** A block reads ``shapevar.field`` (single-object
  access) where ``field`` is neither a SELECT column nor a declared ``computed``
  member of the bound Shape: the value silently renders as ``None`` at runtime.
* **Over-fetch (#166, WARNING — default, promotable).** A Shape column no bound
  block reads. Block coverage is incomplete static information, so this is humble
  by default and can be promoted via ``override_contract_severity``.
* **Un-injectable tenant scope (#169, ERROR — §8.1).** A Shape declares
  ``scope=`` but its declared SQL is opaque/un-injectable (CTE / UNION /
  ``SELECT *`` / no analyzable FROM), so the bounded compiler cannot structurally
  inject the scope predicate and the query would silently leak across tenants.
  The tenant-scope guarantee is delivered by structural injection on the compiler
  *output*, never by a flaky WHERE-column scanner; this is the single
  statically-decidable scope ERROR, reported with an actionable message by
  :func:`_check_scope_injectable`.
* **Un-compilable Shape (#167/#169, ERROR).** Every Shape the app actually uses
  is run through :meth:`chirp.data.Shape.validate` -- the runtime fail-loud
  authority. It asserts the compiler *output* carries the scope predicate for a
  scoped Shape, and that every ``nested()`` child is batchable (analyzable FROM,
  the ``on`` join column present as a child field, the parent ``key`` present).
  A :class:`chirp.data.errors.ShapeError` becomes a startup ERROR so a Shape that
  would crash or silently misbehave at runtime fails ``app.check()`` instead. The
  scope-injectability case is de-duplicated against ``_check_scope_injectable``
  so it fires exactly one ERROR.

Ownership boundary (no double-fire with ``data``): ``data`` matches only
``db.fetch(cls, sql)`` *db-handle* receivers; ``Shape.fetch(...)`` has the
``Shape`` *class* as its receiver, which ``_is_db_receiver`` rejects. The two
categories cannot fire on the same call site.

Conservatism contract (skip-not-guess — this is a fail-loud ERROR category, so a
false positive breaks freeze in debug): the whole body is wrapped so any
unexpected analysis error returns ``[]`` and never crashes ``app.check()``. The
field-level claim is made *only* for single-object ``shapevar.field`` access; the
dominant list/table (``{% for c in rows %}``) and macro-arg patterns collapse to
the collection root in ``depends_on`` and are invisible -- shapecheck verifies the
root is bound, not the per-item fields. Opaque shapes (``SELECT *`` /
expressions / CTE / UNION -> ``columns == ()``) are an explicit escape hatch.

Escape hatches subtracted from a block's reads before any field claim:

* template globals (``url_for``, ``csrf_token``, ``csp_nonce``, ``_``, ``range``,
  ``len`` ...) -- they leak into ``depends_on``;
* block-local bindings (``{% set %}`` / ``let`` / ``export`` / ``capture`` /
  ``def`` / ``region`` / loop targets / def params), collected from the block body;
* the literal context keys ``error`` and ``form`` (reactive ``depends_on`` noise);
* **derived accessors on the Shape dataclass** -- a ``shapevar.name`` read where
  ``name`` is a real class-level attribute (a ``@property``, method, or
  descriptor) on the bound dataclass but not a dataclass field. These are
  idiomatic derived members (the reason to use a dataclass over a tuple); they
  resolve at runtime and render correctly, and the columns they consume live
  *inside* the accessor body where ``depends_on`` cannot see them -- so a
  derived-accessor read also suppresses the per-binding over-fetch claim (its
  column coverage is invisibly incomplete);
* loop-collapsed reads (only the collection root appears, no ``root.field``);
* macro/def-arg reads (the def name leaks; field reads do not);
* opaque shapes;
* templates under ``chirp/`` / ``chirpui/``.

Default severities (ship the proper design): registry-drift = ERROR, under-fetch
= ERROR, over-fetch = WARNING. All overridable via
``app.override_contract_severity("shapecheck", ...)``.
"""

from __future__ import annotations

import ast
import dataclasses
import difflib
import inspect
from typing import TYPE_CHECKING, Any, cast

from .rules_fragment_scope import _binding_names
from .types import ContractIssue, Severity

if TYPE_CHECKING:
    from collections.abc import Mapping

    from chirp.app.state import ContractCheckSnapshot

# Return-type constructors whose first two positionals are
# ``(template, block)`` and whose kwargs carry the render context.
_FRAGMENT_RETURNS = frozenset({"Fragment", "Page", "Suspense"})

# Reactive ``depends_on`` noise: these false context keys are documented
# artifacts of the dependency-analysis work, not real Shape field reads.
# ``__chirp_defer_pending__`` is Suspense's injected shell key (a frozenset,
# never a Shape field), so it is subtracted too.
_DEPS_NOISE = frozenset({"error", "form", "__chirp_defer_pending__"})


@dataclasses.dataclass(frozen=True, slots=True)
class _ShapecheckBinding:
    """Per-binding derived state cached by pass 1 for the pass-2 report.

    Pass 1 resolves each ``(template, block, shapevar, Shape)`` binding to its
    columns / computed / provided fields, occurrence-granular own reads, and
    attribution metadata exactly once; pass 2 emits under-fetch (per binding) and
    over-fetch (against the shape-group read union) from these records.
    """

    template_name: str
    block_name: str
    shapevar: str
    shape_name: str
    columns: tuple[str, ...]
    computed: frozenset[str]
    provided: frozenset[str]
    read_fields: frozenset[str]
    guarded_reads: frozenset[str]
    attribution_blocks: dict[str, frozenset[str]]
    block_depths: dict[str, int]
    # Over-fetch group identity: object identity of the resolved Shape class so
    # two genuinely distinct shapes under one var name never share a union.
    group_key: tuple[str, str, int]


def _dedent(src: str) -> str:
    """Normalize indentation so ``ast.parse`` accepts a nested handler source."""
    return inspect.cleandoc("\n" + src) if src and src[0] in " \t" else src


def _shape_meta(cls: Any) -> Any | None:
    """Return the ``_ShapeMeta`` sidecar on a ``@shape`` class, else ``None``."""
    meta = getattr(cls, "__chirp_shape__", None)
    # Duck-typed: a frozen sidecar exposing columns/computed. Avoids importing
    # chirp.data (keeps this rule importable for db-less / data-less apps).
    if meta is None:
        return None
    if not (hasattr(meta, "columns") and hasattr(meta, "computed")):
        return None
    return meta


def _composite_meta(cls: Any) -> Any | None:
    """Return the ``_CompositeMeta`` sidecar on a ``@composite`` class, else ``None``.

    Duck-typed (a frozen sidecar exposing ``members``) so this rule stays
    importable for db-less / data-less apps, mirroring :func:`_shape_meta`.
    """
    meta = getattr(cls, "__chirp_composite__", None)
    if meta is None:
        return None
    if not hasattr(meta, "members"):
        return None
    return meta


def _composite_field_shape(composite_cls: Any, field: str) -> Any | None:
    """Resolve a composite field name to its member ``@shape`` class, else ``None``.

    A block bound to ``page.field`` (where ``page`` is a ``@composite``) reads the
    fields of that field's member Shape; the per-block subset check then runs
    against the composite member's provided fields -- never one query per block
    (§4-L4). Returns ``None`` when the field is not a Shape member (skip).
    """
    meta = _composite_meta(composite_cls)
    if meta is None:
        return None
    for member in getattr(meta, "members", ()) or ():
        if getattr(member, "field", None) == field:
            shape_cls = getattr(member, "shape_cls", None)
            return shape_cls if _shape_meta(shape_cls) is not None else None
    return None


def _shape_field_names(cls: Any) -> frozenset[str]:
    """Return the dataclass field names of a ``@shape`` class (empty if not one)."""
    if not dataclasses.is_dataclass(cls):
        return frozenset()
    return frozenset(f.name for f in dataclasses.fields(cls))


def _derived_accessors(cls: Any) -> frozenset[str]:
    """Return the Shape's derived accessors -- real attributes, not dataclass fields.

    A ``@shape``-decorated dataclass commonly exposes a ``@property`` or method
    over its columns (``full_name`` over ``first_name``/``last_name``,
    ``url()`` over ``slug``). Such a name is a real class-level attribute (a
    property, function, descriptor, or class var) but NOT a dataclass field --
    reading ``shapevar.full_name`` resolves at runtime and renders correctly, so
    it must never be flagged as an under-fetch. We collect every public
    class-level attribute that is not a dataclass field and not a dunder; the
    columns these accessors consume live inside their bodies, invisible to
    ``depends_on``.

    Uses ``inspect.getattr_static`` so a ``property`` is observed as the
    descriptor object (never triggering its getter against the bare class).
    """
    if not isinstance(cls, type):
        return frozenset()
    fields = _shape_field_names(cls)
    accessors: set[str] = set()
    for name in dir(cls):
        if name.startswith("__") or name in fields:
            continue
        try:
            inspect.getattr_static(cls, name)
        except AttributeError:
            continue
        accessors.add(name)
    return frozenset(accessors)


def _resolve_shape(value: Any, registry: Mapping[str, type]) -> Any | None:
    """Resolve a binding value to a ``@shape`` class.

    Accepts either the class itself or a registry name string. Returns the
    class when it carries a ``_ShapeMeta`` sidecar, else ``None`` (skip).
    """
    if isinstance(value, str):
        value = registry.get(value)
    if value is None:
        return None
    return value if _shape_meta(value) is not None else None


def _string_arg(node: ast.expr | None) -> str | None:
    """Return the value of a string-literal AST node, else ``None``."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _shape_from_call(node: ast.Call, handler_globals: dict[str, Any]) -> Any | None:
    """Resolve ``Shape.fetch(SomeShape, ...)`` to the ``SomeShape`` class.

    Matches ``fetch`` / ``fetch_one`` / ``stream`` on a receiver named ``Shape``
    whose first positional arg is a bare ``Name`` resolvable in handler globals.
    Anything else returns ``None`` (skip -- not statically a Shape fetch).
    """
    func = node.func
    if not isinstance(func, ast.Attribute):
        return None
    if func.attr not in {"fetch", "fetch_one", "stream"}:
        return None
    if not (isinstance(func.value, ast.Name) and func.value.id == "Shape"):
        return None
    if not node.args:
        return None
    first = node.args[0]
    if not isinstance(first, ast.Name):
        return None
    return handler_globals.get(first.id)


def _composite_from_call(node: ast.Call, handler_globals: dict[str, Any]) -> Any | None:
    """Resolve ``Composite.load(SomePage, ...)`` to the ``SomePage`` class.

    Matches ``load`` on a receiver named ``Composite`` whose first positional arg
    is a bare ``Name`` resolvable in handler globals to a ``@composite`` class.
    Anything else returns ``None`` (skip -- not statically a Composite load).
    """
    func = node.func
    if not isinstance(func, ast.Attribute):
        return None
    if func.attr != "load":
        return None
    if not (isinstance(func.value, ast.Name) and func.value.id == "Composite"):
        return None
    if not node.args:
        return None
    first = node.args[0]
    if not isinstance(first, ast.Name):
        return None
    candidate = handler_globals.get(first.id)
    return candidate if _composite_meta(candidate) is not None else None


def _local_shape_bindings(tree: ast.AST, handler_globals: dict[str, Any]) -> dict[str, Any]:
    """Map handler-local names to the Shape class they were assigned from.

    Recognizes ``name = await Shape.fetch(SomeShape, ...)`` and
    ``name = Shape.fetch(SomeShape, ...)`` (and ``fetch_one`` / ``stream``).
    Only single-target ``Name`` assignments are tracked. The resolved value is
    the Shape *class* (from handler globals) -- ``None`` entries are dropped.
    """
    bindings: dict[str, Any] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        value = node.value
        if isinstance(value, ast.Await):
            value = value.value
        if not isinstance(value, ast.Call):
            continue
        shape_cls = _shape_from_call(value, handler_globals)
        if shape_cls is not None:
            bindings[target.id] = shape_cls
    return bindings


def _local_composite_bindings(tree: ast.AST, handler_globals: dict[str, Any]) -> dict[str, Any]:
    """Map handler-local names to the ``@composite`` class they were loaded from.

    Recognizes ``page = await Composite.load(SomePage, ...)`` (and the non-await
    form). Only single-target ``Name`` assignments are tracked. The resolved
    value is the ``@composite`` *class* from handler globals; ``None`` dropped.
    """
    bindings: dict[str, Any] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        value = node.value
        if isinstance(value, ast.Await):
            value = value.value
        if not isinstance(value, ast.Call):
            continue
        composite_cls = _composite_from_call(value, handler_globals)
        if composite_cls is not None:
            bindings[target.id] = composite_cls
    return bindings


def _kwarg_shape(
    kw_value: ast.expr,
    local_shapes: dict[str, Any],
    local_composites: dict[str, Any],
    handler_globals: dict[str, Any],
) -> Any | None:
    """Resolve a render-context kwarg value to a bound Shape class.

    Statically-decidable forms:

    * ``shapevar=some_local`` where ``some_local = await Shape.fetch(S, ...)``;
    * ``shapevar=Shape.fetch(S, ...)`` (inline fetch as the kwarg value);
    * ``shapevar=S`` where ``S`` is a ``@shape`` class in handler globals;
    * ``shapevar=page.field`` where ``page = await Composite.load(P, ...)`` and
      ``field`` is a member Shape of the composite ``P`` (#170) -- the block's
      provided fields come from that composite member's Shape, never one query
      per block.
    """
    if isinstance(kw_value, ast.Await):
        kw_value = kw_value.value
    if isinstance(kw_value, ast.Name):
        if kw_value.id in local_shapes:
            return local_shapes[kw_value.id]
        candidate = handler_globals.get(kw_value.id)
        return candidate if _shape_meta(candidate) is not None else None
    if isinstance(kw_value, ast.Attribute):
        # ``page.field`` -> the composite member Shape for ``field``.
        base = kw_value.value
        if isinstance(base, ast.Name) and base.id in local_composites:
            return _composite_field_shape(local_composites[base.id], kw_value.attr)
        return None
    if isinstance(kw_value, ast.Call):
        return _shape_from_call(kw_value, handler_globals)
    return None


def _static_bindings(
    tree: ast.AST,
    handler_globals: dict[str, Any],
) -> list[tuple[str | None, str, str, Any]]:
    """Recover ``(template, block, shapevar, shape_cls)`` from handler return calls.

    AST-walks the handler for ``Fragment``/``Page``/``Suspense`` calls. The first
    positional is the template, the second positional is the block (both must be
    string literals). Each kwarg whose value resolves to a Shape contributes one
    binding: ``shapevar`` is the kwarg name (the template variable), ``shape_cls``
    is the resolved class. A kwarg value ``page.field`` (where ``page`` is a
    ``Composite.load(...)`` local) resolves to that composite field's member Shape
    -- the per-block subset check runs against the composite member's provided
    fields (#170).
    """
    local_shapes = _local_shape_bindings(tree, handler_globals)
    local_composites = _local_composite_bindings(tree, handler_globals)
    bindings: list[tuple[str | None, str, str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else None
        if name not in _FRAGMENT_RETURNS:
            continue
        template = _string_arg(node.args[0]) if node.args else None
        block = _string_arg(node.args[1]) if len(node.args) >= 2 else None
        if block is None:
            # No statically-known block name -> cannot bind a (template, block).
            continue
        for kw in node.keywords:
            if kw.arg is None:
                continue
            shape_cls = _kwarg_shape(kw.value, local_shapes, local_composites, handler_globals)
            if shape_cls is not None:
                bindings.append((template, block, kw.arg, shape_cls))
    return bindings


def _block_node(env: Any, template_name: str, block_name: str) -> Any | None:
    """Return the kida AST ``Block`` node for ``block_name``, or ``None``."""
    try:
        template = env.get_template(template_name)
    except Exception:
        return None
    ast_root = getattr(template, "_optimized_ast", None)
    if ast_root is None:
        return None
    target = None
    for node in _walk_kida(ast_root):
        if type(node).__name__ == "Block" and getattr(node, "name", None) == block_name:
            target = node
    return target


def _walk_kida(node: Any) -> Any:
    """Depth-first walk of a kida AST yielding every child node."""
    yield node
    for child in _kida_children(node):
        yield from _walk_kida(child)


def _kida_children(node: Any) -> list[Any]:
    """Yield child nodes from the kida-AST container attributes."""
    children: list[Any] = []
    for attr in ("body", "else_", "empty"):
        value = getattr(node, attr, None)
        if isinstance(value, (list, tuple)):
            children.extend(value)
    elif_ = getattr(node, "elif_", None)
    if isinstance(elif_, (list, tuple)):
        for pair in elif_:
            if isinstance(pair, tuple) and len(pair) == 2 and isinstance(pair[1], (list, tuple)):
                children.extend(pair[1])
    cases = getattr(node, "cases", None)
    if isinstance(cases, (list, tuple)):
        for case in cases:
            if isinstance(case, tuple) and len(case) == 3 and isinstance(case[2], (list, tuple)):
                children.extend(case[2])
    return children


def _block_local_names(block_node: Any) -> frozenset[str]:
    """Names bound *inside* a block (subtract before any field claim).

    Walks the block body collecting ``{% set %}`` / ``let`` / ``export`` /
    ``capture`` / ``def`` / ``region`` targets, loop variables, and def params
    via :func:`_binding_names` (the canonical single-node collector). Per §8.5
    #3 we walk the body rather than calling ``_binding_names`` on the block.
    """
    names: set[str] = set()
    for node in _walk_kida(block_node):
        for name, _kind in _binding_names(node):
            if isinstance(name, str):
                names.add(name)
        # Loop targets: ``{% for x in items %}`` binds ``x`` (and tuple targets).
        if type(node).__name__ == "For":
            names.update(_for_target_names(getattr(node, "target", None)))
        # Macro / def params leak field reads behind an arg name -> subtract.
        names.update(_param_names(node))
    return frozenset(names)


def _for_target_names(expr: Any) -> set[str]:
    """Names bound by a kida ``For`` target expression (incl. tuple targets)."""
    if expr is None:
        return set()
    if type(expr).__name__ == "Name":
        name = getattr(expr, "name", None)
        return {name} if isinstance(name, str) else set()
    names: set[str] = set()
    for item in getattr(expr, "items", ()) or ():
        names.update(_for_target_names(item))
    return names


def _param_names(node: Any) -> set[str]:
    """Parameter names declared on a kida ``Def``/``Macro``/``Region`` node."""
    names: set[str] = set()
    for attr in ("params", "args"):
        params = getattr(node, attr, None)
        if not isinstance(params, (list, tuple)):
            continue
        for param in params:
            if isinstance(param, str):
                names.add(param)
            else:
                pname = getattr(param, "name", None)
                if isinstance(pname, str):
                    names.add(pname)
    return names


def _iter_kida_descendants(node: Any) -> Any:
    """Depth-first walk of a kida AST via the native ``iter_child_nodes()``.

    Yields every descendant node (excluding ``node`` itself). Uses kida's own
    :meth:`kida.nodes.base.Node.iter_child_nodes` (dataclass-field
    introspection) rather than this module's hand-rolled ``_kida_children`` so
    the traversal covers every container shape kida defines (``with`` targets,
    ``match`` cases, etc.) with zero parallel-maintenance hazard.
    """
    iter_children = getattr(node, "iter_child_nodes", None)
    if iter_children is None:
        return
    for child in iter_children():
        yield child
        yield from _iter_kida_descendants(child)


def _nested_block_nodes(block_node: Any) -> list[Any]:
    """Return the ``Block`` descendants nested *inside* ``block_node``.

    A parent block's ``depends_on`` is kida's documented conservative SUPERSET:
    it absorbs every nested child block's reads (verified empirically -- a child
    block nested under a ``{% for %}``/``{% if %}`` still bleeds into the parent
    via :class:`kida.analysis.dependencies.DependencyWalker`). Used for
    under-fetch ATTRIBUTION: a flagged path is named against the innermost block
    whose OWN reads contain it, so we need each nested child's name to analyze it
    independently.
    """
    return [node for node in _iter_kida_descendants(block_node) if type(node).__name__ == "Block"]


def _own_reads_walker() -> Any | None:
    """Return a fresh OWN-reads ``DependencyWalker`` subclass instance, or ``None``.

    The walker reuses kida's own :class:`kida.analysis.dependencies.DependencyWalker`
    (the single source of truth for what counts as a context read -- scope
    handling for loop vars / ``{% set %}`` / def params, builtin elision, dotted
    path building) but overrides ``visit_Block`` so that nested (non-root) Block
    nodes are treated as OPAQUE: the root block's body is recursed, but the walker
    does NOT descend into nested child blocks. The result is the block's
    OCCURRENCE-granular own reads -- a dotted read that occurs in BOTH the parent
    body and a nested child is retained (it genuinely lives in the parent), and a
    read that occurs ONLY inside a nested child is excluded (no parent bleed).

    Returns ``None`` when kida's dependency machinery is unavailable (skip-not-
    guess -- this is a fail-loud ERROR category, so an analysis we cannot perform
    must drop to no claim, never a guess).
    """
    try:
        from kida.analysis.dependencies import DependencyWalker
    except Exception:
        return None

    class _OwnReadsWalker(DependencyWalker):  # type: ignore[misc, valid-type]
        """Analyze a Block's OWN reads, treating nested child Blocks as opaque."""

        def __init__(self) -> None:
            super().__init__()
            # The first Block visited is the analyzed (root) block -- recurse it.
            # Every Block reached after that is a nested child -- do not descend.
            self._root_seen = False

        def visit_Block(self, node: Any) -> None:  # noqa: N802
            if self._root_seen:
                return  # nested child block -> opaque, no bleed into the parent
            self._root_seen = True
            for child in getattr(node, "body", ()) or ():
                self.visit(child)

    return _OwnReadsWalker()


def _own_block_reads(
    env: Any,
    template_name: str,
    block_name: str,
) -> frozenset[str] | None:
    """Return ``block_name``'s OWN reads, pruned of nested-child bleed.

    kida's ``depends_on`` for a parent block is a conservative SUPERSET that
    absorbs every nested child block's reads. Naive ``own = depends_on(parent) -
    union(depends_on(child))`` (set difference of analysis sets) is a
    FALSE-NEGATIVE hazard: kida's ``depends_on`` is set-granularity, so when the
    SAME dotted read (e.g. ``board.owner``) occurs in BOTH the parent body AND a
    nested child under the same shapevar, subtraction removes it from the parent
    ENTIRELY -- a genuine parent under-fetch is silently MISSED.

    We instead compute own reads at OCCURRENCE granularity by reusing kida's own
    :class:`kida.analysis.dependencies.DependencyWalker` with ``visit_Block``
    overridden to treat nested child Blocks as opaque (see
    :func:`_own_reads_walker`). A read in both the parent body and a nested child
    is retained on the parent; a read ONLY in a nested child is excluded. This
    fires the marquee parent under-fetch without re-introducing nested-child
    bleed.

    Returns ``None`` when the template/block/walker cannot be analyzed (skip).
    kida's reads are treated strictly as a conservative superset -- this rule
    never assumes kida prunes.
    """
    block_node = _block_node(env, template_name, block_name)
    if block_node is None:
        return None
    walker = _own_reads_walker()
    if walker is None:
        return None
    try:
        return frozenset(walker.analyze(block_node))
    except Exception:
        return None


def _own_reads_by_block(
    env: Any,
    template_name: str,
    block_names: frozenset[str],
) -> dict[str, frozenset[str]]:
    """Map each of ``block_names`` to its OWN (bleed-pruned) reads.

    Used for under-fetch attribution: a flagged read path is reported against
    the innermost block whose OWN reads contain it, not the bound ancestor
    block. Blocks that cannot be analyzed are simply absent from the map.
    """
    result: dict[str, frozenset[str]] = {}
    for name in block_names:
        own = _own_block_reads(env, template_name, name)
        if own is not None:
            result[name] = own
    return result


def _block_depths(env: Any, template_name: str, block_name: str) -> dict[str, int]:
    """Map the bound block + each nested descendant block to its nesting depth.

    The bound block is depth 0; a block nested one level deeper is depth 1, etc.
    Used by :func:`_innermost_owner` to break attribution ties toward the
    syntactically-innermost block. Returns ``{}`` when the block cannot be found.
    """
    block_node = _block_node(env, template_name, block_name)
    if block_node is None:
        return {}
    depths: dict[str, int] = {}
    name = getattr(block_node, "name", None)
    if isinstance(name, str):
        depths[name] = 0

    def _descend(node: Any, depth: int) -> None:
        for child in getattr(node, "iter_child_nodes", lambda: ())():
            if type(child).__name__ == "Block":
                child_name = getattr(child, "name", None)
                if isinstance(child_name, str):
                    # Last-wins on duplicate names mirrors kida's metadata dict.
                    depths[child_name] = depth + 1
                _descend(child, depth + 1)
            else:
                _descend(child, depth)

    _descend(block_node, 0)
    return depths


def _innermost_owner(
    read_path: str,
    own_reads_by_block: dict[str, frozenset[str]],
    block_depths: dict[str, int],
    fallback: str,
    bound_blocks: frozenset[str],
) -> str:
    """Return the innermost BOUND block whose OWN reads contain ``read_path``.

    Attribution must name a block whose Shape contract was actually verified --
    i.e. a block in ``bound_blocks`` (the set of blocks this app binds to a
    Shape). The innermost owner of a flagged read may be an UNBOUND nested child
    (e.g. a ``{% block badge %}`` nested inside a bound ``{% block header %}`` that
    shares the read): naming that sibling/child points the developer at a block
    whose contract was never checked, when the failure belongs to the BOUND
    binding (``header``). So we restrict to bound owners and pick the innermost of
    those; the read still fires (no false negative) -- only the reported block
    name changes to a verified binding.

    Ties (same depth) are unlikely (a given read lives in one block); when no
    bound block claims the path -- e.g. a duplicate-name AST/metadata shadow made
    the bound block's own-reads diverge -- attribute to ``fallback`` (the bound
    block being checked) so a real under-fetch is never silently dropped.
    """
    owners = [
        name
        for name, reads in own_reads_by_block.items()
        if read_path in reads and name in bound_blocks
    ]
    if not owners:
        return fallback
    return max(owners, key=lambda name: block_depths.get(name, 0))


def _default_none_guarded_reads(block_node: Any) -> frozenset[str]:
    """Return ``shapevar.field`` paths in a block guarded by ``| default(none)``.

    Used for #11: the under-fetch remediation hint only tells the author to
    delete the ``| default(none)`` guard when the flagged read actually carries
    one. A guard appears in the kida AST as a ``Filter(name='default')`` wrapping
    a ``Getattr(obj=Name, attr=...)`` whose sole positional arg is the ``None``
    constant. We record the dotted ``obj.attr`` path for each such filter.
    """
    if block_node is None:
        return frozenset()
    guarded: set[str] = set()
    for node in _iter_kida_descendants(block_node):
        if type(node).__name__ != "Filter":
            continue
        if getattr(node, "name", None) != "default":
            continue
        args = cast(tuple[Any, ...], getattr(node, "args", ()) or ())
        # Only a ``default(none)`` (single ``None`` constant) guard is the one
        # the hint references; ``default('fallback')`` is a different intent.
        if len(args) != 1:
            continue
        arg = args[0]
        if not (type(arg).__name__ == "Const" and getattr(arg, "value", object()) is None):
            continue
        value = getattr(node, "value", None)
        if type(value).__name__ != "Getattr":
            continue
        obj = getattr(value, "obj", None)
        attr = getattr(value, "attr", None)
        if type(obj).__name__ == "Name" and isinstance(attr, str):
            base = getattr(obj, "name", None)
            if isinstance(base, str):
                guarded.add(f"{base}.{attr}")
    return frozenset(guarded)


def _binding_read_fields(
    reads: frozenset[str],
    shapevar: str,
    accessors: frozenset[str],
    env_globals: frozenset[str],
    local_names: frozenset[str],
) -> tuple[set[str], bool]:
    """Extract the ``shapevar.field`` reads of a single binding.

    Returns ``(read_fields, read_accessor)``: the set of first-attr field names
    read off ``shapevar`` (after subtracting noise / globals / block-locals and
    derived accessors), and whether any read resolved to a derived accessor (a
    ``@property`` / method / descriptor). A derived-accessor read makes the
    binding's column coverage invisibly incomplete -- the over-fetch claim is
    suppressed for the whole shape group when any binding read one.

    Shared by the over-fetch group-union pre-pass and the per-binding under-fetch
    pass so both observe identical read-field semantics (no parallel drift).
    """
    read_fields: set[str] = set()
    read_accessor = False
    for path in reads:
        parts = path.split(".")
        if parts[0] != shapevar:
            continue
        if len(parts) < 2:
            # Bare ``shapevar`` (loop-collapsed root read) -> no field claim.
            continue
        field = parts[1]
        # #10: noise / template-global / block-local names are bare context KEYS
        # (parts[0], the shapevar root), never the ``.field`` attribute. Keying
        # off the attribute (parts[1]) would make a Shape column named ``form`` /
        # ``error`` / ``__chirp_defer_pending__`` silently uncheckable. The
        # shapevar root reaching here is already not in those sets (it is a bound
        # Shape var), so the field is checked.
        if parts[0] in _DEPS_NOISE or parts[0] in env_globals or parts[0] in local_names:
            continue
        # Deeper segments (v.a.b -> only 'a') are never checked.
        if field in accessors:
            # Derived accessor (@property / method / descriptor): resolves at
            # runtime, not a column typo. Skip the field claim and remember that
            # this binding read one -> its over-fetch is unreliable.
            read_accessor = True
            continue
        read_fields.add(field)
    return read_fields, read_accessor


def _check_registry_drift(
    surface_contracts: Mapping[str, Any],
    registry: Mapping[str, type],
) -> list[ContractIssue]:
    """Flag surface-contract names whose target resolves to no registered Shape.

    ``surface_contracts`` maps a surface name -> the expected Shape name. A
    target absent from :func:`chirp.data.shape_registry` is drift (a typo or a
    renamed-away view). Emits one ERROR per drifted surface, with a
    :func:`difflib.get_close_matches` suggestion from the live registry names.
    """
    issues: list[ContractIssue] = []
    known = sorted(registry.keys())
    for surface, target in surface_contracts.items():
        if not isinstance(surface, str) or not isinstance(target, str):
            continue
        if target in registry:
            continue
        suggestions = difflib.get_close_matches(target, known, n=1)
        hint = f" Did you mean '{suggestions[0]}'?" if suggestions else ""
        issues.append(
            ContractIssue(
                severity=Severity.ERROR,
                category="shapecheck",
                message=(
                    f"Surface contract '{surface}' names Shape '{target}', but no "
                    "such Shape is registered."
                ),
                details=(
                    f"Register a @shape-decorated row model named '{target}', or "
                    f"fix the surface-contract name.{hint}"
                ),
            )
        )
    return issues


def _check_scope_injectable(
    shapes: set[type],
    flagged_names: set[str] | None = None,
) -> list[ContractIssue]:
    """Flag scoped Shapes whose SQL is opaque/un-injectable (#169, §8.1 #3).

    The tenant-scope guarantee is delivered by structural injection on the
    compiler output -- not a WHERE scan. The ONE statically-decidable ERROR is
    reserved for a Shape that declares ``scope=`` but whose declared SQL is
    opaque/un-injectable (CTE / UNION / SELECT * / no analyzable FROM), so the
    compiler CANNOT inject the predicate and the query would silently leak
    across tenants. We delegate the injectability decision to the compiler's own
    :func:`chirp.data.shapes._scope_injectable` (single source of truth, no
    WHERE-column scanner).

    Scoped only over ``shapes`` -- the set of Shapes this app actually uses
    (route-bound + resolved surface-contract targets). Iterating the entire
    process-wide registry would leak unrelated test/app fixtures into every
    other app's ``app.check()``; an app's scope contract is about the Shapes the
    app binds, not every Shape ever imported.

    ``flagged_names``: when given, every Shape name this check ERRORs on is added
    to it so the caller can de-dup the :func:`_check_shape_validate` pass (whose
    ``Shape.validate`` would raise the same scope failure with a less actionable
    message).
    """
    try:
        from chirp.data.shapes import _scope_injectable
    except Exception:
        return []

    issues: list[ContractIssue] = []
    seen: set[str] = set()
    for cls in shapes:
        meta = _shape_meta(cls)
        if meta is None:
            continue
        scope = getattr(meta, "scope", None)
        if scope is None:
            continue
        sql = getattr(meta, "sql", None)
        if not isinstance(sql, str):
            continue
        if _scope_injectable(sql):
            continue
        shape_name = getattr(meta, "name", None) or getattr(cls, "__name__", "Shape")
        if shape_name in seen:
            continue
        seen.add(shape_name)
        if flagged_names is not None:
            flagged_names.add(shape_name)
        issues.append(
            ContractIssue(
                severity=Severity.ERROR,
                category="shapecheck",
                message=(
                    f"Shape '{shape_name}' declares scope='{scope}', but its SQL is "
                    "opaque/un-injectable (CTE / UNION / SELECT * / no analyzable "
                    "FROM): the tenant-scope predicate cannot be structurally injected."
                ),
                details=(
                    "Rewrite the SQL as a simple single SELECT with an analyzable "
                    f"FROM (and an explicit column list), or add 'WHERE {scope} = "
                    ":scope' to a form the compiler can extend. The scope guarantee "
                    "is unconditional: an un-injectable scoped Shape would silently "
                    "query across tenants."
                ),
            )
        )
    return issues


def _shape_name(cls: Any) -> str:
    """Best-effort registry/class name for a Shape (for de-dup and messages)."""
    meta = _shape_meta(cls)
    if meta is not None:
        name = getattr(meta, "name", None)
        if isinstance(name, str) and name:
            return name
    return getattr(cls, "__name__", "Shape")


def _check_shape_validate(
    shapes: set[type],
    already_flagged: set[str],
) -> list[ContractIssue]:
    """Run :meth:`chirp.data.Shape.validate` over every USED Shape (#169/#167).

    ``Shape.validate`` is the runtime fail-loud authority: for a scoped Shape it
    asserts the compiler OUTPUT carries the scope predicate, and for nested
    children it asserts each child is batchable (analyzable FROM, the ``on`` join
    column present as a field, the parent ``key`` present). A
    :class:`chirp.data.errors.ShapeError` is the decoration-time signal that a
    Shape cannot be safely compiled -- it would crash or silently misbehave at
    runtime, so we surface it as a startup ``app.check()`` ERROR.

    De-dup: the scope-injectability case is already reported by
    :func:`_check_scope_injectable` with a more actionable message; shapes whose
    name is in ``already_flagged`` are skipped here so a scoped-opaque Shape
    fires exactly one ERROR (not the generic validate echo too). Anything
    ``Shape.validate`` rejects that the scope check did NOT (a malformed nested
    child) still surfaces here.
    """
    try:
        from chirp.data import Shape
        from chirp.data.errors import ShapeError
    except Exception:
        return []

    issues: list[ContractIssue] = []
    seen: set[str] = set()
    for cls in shapes:
        if _shape_meta(cls) is None:
            continue
        name = _shape_name(cls)
        if name in already_flagged or name in seen:
            continue
        try:
            Shape.validate(cls)
        except ShapeError as exc:
            seen.add(name)
            issues.append(
                ContractIssue(
                    severity=Severity.ERROR,
                    category="shapecheck",
                    message=(f"Shape '{name}' cannot be safely compiled: {exc}"),
                    details=(
                        "Shape.validate rejected this Shape at startup -- it would "
                        "fail or silently misbehave at runtime. Fix the declared SQL "
                        "or nested() child declaration as the message describes."
                    ),
                )
            )
        except Exception:
            # Non-ShapeError failures are not this rule's contract; skip rather
            # than crash app.check() (the body-wrapper would swallow it anyway).
            continue
    return issues


def check_shapecheck(snapshot: ContractCheckSnapshot) -> list[ContractIssue]:
    """Verify ``@shape`` render bindings and surface-contract registry drift.

    See the module docstring for the full claim set, ownership boundary, escape
    hatches, and conservatism contract. The entire body is wrapped so any
    unexpected analysis error returns ``[]`` -- a built-in rule must never crash
    ``app.check()``.
    """
    try:
        return _check_shapecheck(snapshot)
    except Exception:
        return []


def _check_shapecheck(snapshot: ContractCheckSnapshot) -> list[ContractIssue]:
    # Auto-registry is always available (import-time registration). Never
    # subscript snapshot.extras -- a bare extras["..."] would KeyError and,
    # because the wrapper swallows it, silently disable the whole rule.
    from chirp.data.shapes import shape_registry

    registry = shape_registry()
    surface_contracts = snapshot.extras.get("surface_contracts", {})
    explicit_bindings = snapshot.extras.get("shapecheck_bindings", {})

    issues: list[ContractIssue] = []

    # --- Registry drift (#166, ERROR) -- runs with or without any extras. ---
    if isinstance(surface_contracts, dict):
        issues.extend(_check_registry_drift(surface_contracts, registry))

    # Shapes this app actually uses (for the scope-injectability check): every
    # surface-contract target that resolves to a real registered Shape. Route
    # bindings (collected below) are added to this set too.
    used_shapes: set[type] = set()
    if isinstance(surface_contracts, dict):
        for target in surface_contracts.values():
            resolved = _resolve_shape(target, registry)
            if resolved is not None:
                used_shapes.add(resolved)

    kida_env = snapshot.kida_env
    if kida_env is None:
        # Field-level checks need template metadata. Registry drift already ran;
        # the scope check + Shape.validate run over the surface-contract-resolved
        # Shapes (de-dup: scope failures are reported once by the scope check).
        scope_flagged: set[str] = set()
        issues.extend(_check_scope_injectable(used_shapes, scope_flagged))
        issues.extend(_check_shape_validate(used_shapes, scope_flagged))
        return issues

    env_globals = frozenset(kida_env.globals) if hasattr(kida_env, "globals") else frozenset()

    # --- Collect (template, block, shapevar, shape_cls) bindings. ---
    # The template element is non-optional here: only bindings whose template
    # statically resolves (call positional or route fallback) are appended, so
    # the field-verification loop below can treat ``template_name`` as ``str``.
    bindings: list[tuple[str, str, str, Any]] = []
    router = snapshot.router
    route_templates = snapshot.route_templates
    for route in getattr(router, "routes", []) or []:
        handler = getattr(route, "handler", None)
        page_src = getattr(route, "page_source_handler", None)
        handler_for_source = page_src if page_src is not None else handler
        if handler_for_source is None:
            continue
        try:
            src = inspect.getsource(handler_for_source)
            tree = ast.parse(_dedent(src))
        except TypeError, OSError, SyntaxError:
            # #12: the handler source is unavailable (C-extension, dynamically
            # built, lambda, REPL-defined) or unparseable -> we cannot recover
            # its Shape bindings. Surface an INFO so a developer wondering why a
            # route is unverified sees it was skipped, rather than silently
            # dropping every binding for the route with no diagnostic.
            route_path = getattr(route, "path", "") or "<unknown>"
            handler_label = getattr(handler_for_source, "__qualname__", None) or getattr(
                handler_for_source, "__name__", repr(handler_for_source)
            )
            issues.append(
                ContractIssue(
                    severity=Severity.INFO,
                    category="shapecheck",
                    message=(
                        f"shapecheck skipped route '{route_path}': handler "
                        f"'{handler_label}' source is unavailable or unparseable, so "
                        "its Shape render bindings could not be statically analyzed."
                    ),
                    details=(
                        "Define the handler at module top level (so inspect.getsource "
                        "can read it), or register the binding explicitly via "
                        "set_contract_check_data('shapecheck_bindings', {(template, "
                        "block): ShapeOrName}) to field-verify it."
                    ),
                )
            )
            continue
        handler_globals = getattr(handler_for_source, "__globals__", {})
        path = getattr(route, "path", "") or ""
        route_template = route_templates.get(path)
        for template, block, shapevar, shape_cls in _static_bindings(tree, handler_globals):
            # route_templates only narrows the template; the return call carries
            # the block. Fall back to the route's template when the call's
            # template positional was not a string literal.
            resolved_template = template if template is not None else route_template
            if resolved_template is None:
                continue
            bindings.append((resolved_template, block, shapevar, shape_cls))

    # --- Explicit binding escape hatch: {(template, block): ShapeClassOrName}. ---
    if isinstance(explicit_bindings, dict):
        for key, value in explicit_bindings.items():
            if not (isinstance(key, tuple) and len(key) == 2):
                continue
            template, block = key
            if not (isinstance(template, str) and isinstance(block, str)):
                continue
            shape_cls = _resolve_shape(value, registry)
            if shape_cls is None:
                continue
            # Explicit bindings need a var name; the convention is that the
            # template binds the shape under the block name's data var. Without
            # a kwarg name we cannot field-check, so the explicit form binds
            # under the Shape's lowercased name as the var. We instead record
            # it with an empty var sentinel: field checks are skipped, but the
            # binding is still verified-counted (root provided).
            bindings.append((template, block, "", shape_cls))

    # Route/explicit-bound Shapes count as "used" for the scope check too.
    for _t, _b, _v, bound_cls in bindings:
        if isinstance(bound_cls, type):
            used_shapes.add(bound_cls)

    # Blocks this app actually BINDS to a Shape, per template. Under-fetch
    # attribution names the innermost owning block, but only among bound blocks
    # (a binding whose contract was verified) -- an unbound nested child that
    # merely shares a read must not be named (R3-6).
    bound_blocks_by_template: dict[str, set[str]] = {}
    for tmpl, blk, _v, _cls in bindings:
        bound_blocks_by_template.setdefault(tmpl, set()).add(blk)

    # --- Tenant-scope injectability (#169, ERROR) over the app's used Shapes. ---
    scope_flagged: set[str] = set()
    issues.extend(_check_scope_injectable(used_shapes, scope_flagged))
    # --- Shape.validate fail-loud (#167/#169) over the app's used Shapes. ---
    issues.extend(_check_shape_validate(used_shapes, scope_flagged))

    # --- Per-binding field verification (two passes). ---
    #
    # Pass 1 computes every binding's derived state once and accumulates the
    # over-fetch group union: a column is "used" if ANY binding of the SAME shape
    # (same template + shapevar + resolved Shape) reads it. R3/round-2 switched
    # over-fetch's read set from kida's depends_on SUPERSET to occurrence-granular
    # OWN reads -- correct for under-fetch attribution, but it widened over-fetch:
    # a column the parent block SELECTs that is read only by a nested CHILD block
    # bound to the SAME shape would false-fire over-fetch on the parent (F7). The
    # union read set restores soundness: the column is consumed by a binding of
    # the shape, so neither block over-fetches it. A derived-accessor read in ANY
    # binding of the group makes the group's column coverage invisibly incomplete,
    # so over-fetch is suppressed group-wide.
    verified = 0
    states: list[_ShapecheckBinding] = []
    # Over-fetch group union: (template, shapevar, id(shape)) -> read_fields union.
    group_reads: dict[tuple[str, str, int], set[str]] = {}
    # Any derived-accessor read in the group suppresses its over-fetch entirely.
    group_accessor: dict[tuple[str, str, int], bool] = {}
    for template_name, block_name, shapevar, shape_cls in bindings:
        if template_name.startswith(("chirp/", "chirpui/")):
            continue
        meta = _shape_meta(shape_cls)
        if meta is None:
            continue
        columns = tuple(getattr(meta, "columns", ()) or ())
        if not columns:
            # Opaque shape (SELECT * / expression / CTE / UNION) -> escape hatch.
            continue
        computed = frozenset(getattr(meta, "computed", frozenset()) or frozenset())
        # #1: a ``nested()`` child field (e.g. ``cards`` on a Board) is a real
        # dataclass field the bounded compiler fills, NOT a SELECT column -- so a
        # ``{% for c in board.cards %}`` read of the collection root must NOT
        # false-fire under-fetch. Union each NestedShape.field into ``provided``.
        # ``meta`` is duck-typed, so reach for ``nested`` defensively.
        nested_fields = frozenset(
            n.field
            for n in (getattr(meta, "nested", ()) or ())
            if isinstance(getattr(n, "field", None), str)
        )
        provided = frozenset(set(columns) | set(computed) | set(nested_fields))
        shape_name = getattr(meta, "name", None) or getattr(shape_cls, "__name__", "Shape")
        # Derived accessors (@property / method / descriptor on the dataclass)
        # are idiomatic and resolve at runtime -> never an under-fetch. The
        # columns they consume live inside the accessor body, invisible to
        # depends_on, so reading one also makes the over-fetch claim unreliable.
        accessors = _derived_accessors(shape_cls)

        # #2: the bound block's ``depends_on`` is kida's conservative SUPERSET --
        # it absorbs every nested child block's reads. Compute the bound block's
        # OWN reads (depends_on minus nested-child depends_on) for the field
        # claim, and the per-descendant-block own reads for ATTRIBUTION (an
        # under-fetch is named against the innermost block where the read
        # syntactically lives, not the bound ancestor).
        reads = _own_block_reads(kida_env, template_name, block_name)
        if reads is None:
            continue

        block_node = _block_node(kida_env, template_name, block_name)
        local_names = _block_local_names(block_node) if block_node is not None else frozenset()
        guarded_reads = _default_none_guarded_reads(block_node)

        # Own reads for the bound block AND every nested descendant block, so a
        # flagged path is attributed to the innermost owning block.
        descendant_names = frozenset(
            name
            for name in (getattr(child, "name", None) for child in _nested_block_nodes(block_node))
            if isinstance(name, str)
        )
        attribution_blocks = _own_reads_by_block(
            kida_env, template_name, frozenset({block_name}) | descendant_names
        )
        # Depth of each block (the bound block is depth 0; deeper = innermost) so
        # ties resolve to the syntactically-innermost block.
        block_depths = _block_depths(kida_env, template_name, block_name)

        verified += 1

        if not shapevar:
            # Explicit binding without a var name -> root-only verification.
            continue

        # Field-level reads: ``shapevar.field`` (after noise/global/local subtract
        # and derived-accessor elision). Shared with the over-fetch group union.
        read_fields, read_accessor = _binding_read_fields(
            reads, shapevar, accessors, env_globals, local_names
        )

        group_key = (template_name, shapevar, id(shape_cls))
        group_reads.setdefault(group_key, set()).update(read_fields)
        group_accessor[group_key] = group_accessor.get(group_key, False) or read_accessor

        states.append(
            _ShapecheckBinding(
                template_name=template_name,
                block_name=block_name,
                shapevar=shapevar,
                shape_name=shape_name,
                columns=columns,
                computed=computed,
                provided=provided,
                read_fields=frozenset(read_fields),
                guarded_reads=guarded_reads,
                attribution_blocks=attribution_blocks,
                block_depths=block_depths,
                group_key=group_key,
            )
        )

    # Pass 2 reports under-fetch (per-binding) and over-fetch (group union).
    #
    # The dedup ``seen`` key carries the resolved Shape NAME (F6): after R3-6
    # attribution two GENUINELY DISTINCT bound shapes that share a var name and an
    # attributed block (e.g. a bound parent on ShapeA and a bound nested child on
    # ShapeB, each missing the same field name) would otherwise collide on
    # (template, block, var, field) and the second real ERROR would be silently
    # dropped. Including the shape identity reports them separately while still
    # de-duplicating genuine duplicates (same shape+var+field reported once).
    seen: set[tuple[str, ...]] = set()
    for st in states:
        # Field-level under-fetch: ``shapevar.field`` where field not provided.
        for field in sorted(st.read_fields):
            if field in st.provided:
                continue
            # #2 attribution: name the innermost block whose OWN reads carry the
            # flagged ``shapevar.field`` path (it may be a nested child block, not
            # the bound ancestor). Fall back to the bound block when no owner is
            # found (defensive; the bound block's own reads contain it by
            # construction unless a duplicate-name shadow intervened).
            read_path = f"{st.shapevar}.{field}"
            syntactic_block = _innermost_owner(
                read_path,
                st.attribution_blocks,
                st.block_depths,
                st.block_name,
                frozenset(bound_blocks_by_template.get(st.template_name, ())),
            )
            key = (st.template_name, syntactic_block, st.shapevar, field, st.shape_name)
            if key in seen:
                continue
            seen.add(key)
            # #11: only suggest deleting the ``| default(none)`` guard when the
            # flagged read actually carries one.
            guard_hint = (
                " then delete the '| default(none)' guard." if read_path in st.guarded_reads else ""
            )
            issues.append(
                ContractIssue(
                    severity=Severity.ERROR,
                    category="shapecheck",
                    message=(
                        f"Block '{syntactic_block}' reads '{st.shapevar}.{field}', but "
                        f"Shape '{st.shape_name}' neither fetched nor declared "
                        f"'{field}'."
                    ),
                    template=st.template_name,
                    details=(
                        f"Add '{field}' to the SELECT, or declare it computed via "
                        f"@shape(..., computed=('{field}',));{guard_hint} "
                        f"Shape provides: {', '.join(sorted(st.provided))}."
                    ),
                )
            )

        # Over-fetch (WARNING, default): a provided column NO binding of the shape
        # reads. Block coverage is incomplete, so this is humble -- only the
        # columns (not declared computed, which are intentionally render-only) are
        # checked. A derived-accessor read in any binding of the group makes
        # coverage invisibly incomplete (the accessor body may consume any
        # column), so over-fetch is suppressed group-wide rather than emit
        # spurious "never reads" noise.
        if group_accessor.get(st.group_key, False):
            continue
        # F7: a column is "used" if ANY binding of the shape (same template +
        # shapevar) reads it -- not just this block's own reads. Otherwise a
        # column read solely by a nested child block bound to the SAME shape
        # false-fires over-fetch on the parent.
        union_reads = group_reads.get(st.group_key, set())
        unread = set(st.columns) - union_reads
        # Subtract computed: declared-computed members are render-side and not
        # expected to be a column read; only flag genuine fetched-but-unread.
        unread -= set(st.computed)
        for column in sorted(unread):
            key = (st.template_name, st.block_name, st.shapevar, f"#over:{column}", st.shape_name)
            if key in seen:
                continue
            seen.add(key)
            issues.append(
                ContractIssue(
                    severity=Severity.WARNING,
                    category="shapecheck",
                    message=(
                        f"Block '{st.block_name}' never reads Shape '{st.shape_name}' "
                        f"column '{column}' (provided by the SELECT)."
                    ),
                    template=st.template_name,
                    details=(
                        "Static block coverage is incomplete (loop/macro reads are "
                        "invisible), so this is a WARNING. If the column is genuinely "
                        "unused, drop it from the SELECT; otherwise ignore. Promote "
                        "via override_contract_severity('shapecheck', Severity.ERROR)."
                    ),
                )
            )

    # PASS line: one INFO when bindings verified clean and NO shapecheck ERROR
    # fired (registry drift or under-fetch). Mirrors §4-L2 #10 -- chirp has no
    # "PASS per category" convention, so an INFO issue surfaces the count.
    has_error = any(i.severity is Severity.ERROR for i in issues)
    if verified > 0 and not has_error:
        issues.append(
            ContractIssue(
                severity=Severity.INFO,
                category="shapecheck",
                message=(
                    f"PASS shapecheck: {verified} verified "
                    f"(template, block, Shape) binding{'s' if verified != 1 else ''}."
                ),
            )
        )

    return issues
