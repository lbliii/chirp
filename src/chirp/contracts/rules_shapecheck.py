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
  *output* (asserted by :meth:`chirp.data.Shape.validate`), never by a flaky
  WHERE-column scanner; this is the single statically-decidable scope ERROR.

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
from typing import TYPE_CHECKING, Any

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


def _leaf_block_reads(env: Any, template_name: str, block_name: str) -> frozenset[str] | None:
    """Return the bound block's ``depends_on`` paths, pruned of ancestor bleed.

    A parent block in the AST accumulates the full dependency set of its
    children. When both a parent and ``block_name`` carry the same dotted path,
    the parent's superset would pollute the leaf claim. We keep ``block_name``'s
    own ``depends_on`` only -- it IS the leaf for this binding. Returns ``None``
    when the template/block cannot be analyzed (skip).
    """
    try:
        template = env.get_template(template_name)
        metadata = template.block_metadata()
    except Exception:
        return None
    block_meta = metadata.get(block_name)
    if block_meta is None:
        return None
    return frozenset(getattr(block_meta, "depends_on", ()))


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


def _check_scope_injectable(shapes: set[type]) -> list[ContractIssue]:
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
        # the scope check runs over the surface-contract-resolved Shapes.
        issues.extend(_check_scope_injectable(used_shapes))
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

    # --- Tenant-scope injectability (#169, ERROR) over the app's used Shapes. ---
    issues.extend(_check_scope_injectable(used_shapes))

    # --- Per-binding field verification. ---
    verified = 0
    seen: set[tuple[str, str, str, str]] = set()
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
        provided = set(columns) | set(computed)
        shape_name = getattr(meta, "name", None) or getattr(shape_cls, "__name__", "Shape")
        # Derived accessors (@property / method / descriptor on the dataclass)
        # are idiomatic and resolve at runtime -> never an under-fetch. The
        # columns they consume live inside the accessor body, invisible to
        # depends_on, so reading one also makes the over-fetch claim unreliable.
        accessors = _derived_accessors(shape_cls)

        reads = _leaf_block_reads(kida_env, template_name, block_name)
        if reads is None:
            continue

        block_node = _block_node(kida_env, template_name, block_name)
        local_names = _block_local_names(block_node) if block_node is not None else frozenset()

        verified += 1

        if not shapevar:
            # Explicit binding without a var name -> root-only verification.
            continue

        # Field-level under-fetch: ``shapevar.field`` where field not provided.
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
            # Deeper segments (v.a.b -> only 'a') are never checked.
            if field in _DEPS_NOISE or field in env_globals or field in local_names:
                continue
            if field in accessors:
                # Derived accessor (@property / method / descriptor): resolves at
                # runtime, not a column typo. Skip the field claim and remember
                # that this binding read one -> its over-fetch is unreliable.
                read_accessor = True
                continue
            read_fields.add(field)

        for field in sorted(read_fields):
            if field in provided:
                continue
            key = (template_name, block_name, shapevar, field)
            if key in seen:
                continue
            seen.add(key)
            issues.append(
                ContractIssue(
                    severity=Severity.ERROR,
                    category="shapecheck",
                    message=(
                        f"Block '{block_name}' reads '{shapevar}.{field}', but Shape "
                        f"'{shape_name}' neither fetched nor declared '{field}'."
                    ),
                    template=template_name,
                    details=(
                        f"Add '{field}' to the SELECT, or declare it computed via "
                        f"@shape(..., computed=('{field}',)); then delete the "
                        "'| default(none)' guard. Shape provides: "
                        f"{', '.join(sorted(provided))}."
                    ),
                )
            )

        # Over-fetch (WARNING, default): a provided column no block reads. Block
        # coverage is incomplete, so this is humble -- only the columns (not
        # declared computed, which are intentionally render-only) are checked.
        # A derived-accessor read makes coverage invisibly incomplete (the
        # accessor body may consume any column), so suppress over-fetch entirely
        # for this binding rather than emit spurious "never reads" noise.
        if read_accessor:
            continue
        unread = set(columns) - read_fields
        # Subtract computed: declared-computed members are render-side and not
        # expected to be a column read; only flag genuine fetched-but-unread.
        unread -= set(computed)
        for column in sorted(unread):
            key = (template_name, block_name, shapevar, f"#over:{column}")
            if key in seen:
                continue
            seen.add(key)
            issues.append(
                ContractIssue(
                    severity=Severity.WARNING,
                    category="shapecheck",
                    message=(
                        f"Block '{block_name}' never reads Shape '{shape_name}' "
                        f"column '{column}' (provided by the SELECT)."
                    ),
                    template=template_name,
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
