"""Private Suspense defer execution DAG compiled at the freeze boundary.

Extends Suspense block discovery + ancestor pruning into an explicit per-route
execution DAG (nodes = defer keys / leaf blocks; edges = ``feeds`` /
``couples``). Stored on runtime state for concurrent resolution and the
``defer_coupling`` independence contract (#949). Not a public return type or
inspection API.
"""

from __future__ import annotations

import ast
import hashlib
import inspect
import logging
import re
from dataclasses import dataclass
from typing import Any, Literal

from chirp.errors import ConfigurationError
from chirp.templating.suspense import DeferExecutionPlan, plan_defer_execution

from .hypermedia_program import HypermediaProgram, SourceOrigin, stable_identity

type _DeferEdgeKind = Literal["feeds", "couples"]

_logger = logging.getLogger("chirp.app.suspense_dag")
_RESERVED_SUSPENSE_KW = frozenset({"defer_map", "defer_blocks", "error_block"})
_DEFER_PENDING_DECL = re.compile(
    r"""['"]([A-Za-z_][A-Za-z0-9_]*)['"]\s+in\s+__chirp_defer_pending__""",
)
_DEFERRED_TEST = re.compile(
    r"""\b([A-Za-z_][A-Za-z0-9_]*)\s+is\s+(?:not\s+)?deferred\b""",
)


@dataclass(frozen=True, slots=True)
class _DeferKeyNode:
    id: str
    key: str
    template_id: str
    route_id: str
    origin: SourceOrigin


@dataclass(frozen=True, slots=True)
class _DeferBlockNode:
    id: str
    name: str
    template_id: str
    route_id: str
    origin: SourceOrigin


@dataclass(frozen=True, slots=True)
class _DeferEdge:
    id: str
    kind: _DeferEdgeKind
    source_id: str
    destination_id: str
    resolved: bool
    origin: SourceOrigin


@dataclass(frozen=True, slots=True)
class _SuspenseRoutePlan:
    """One route's compiled Suspense defer plan."""

    id: str
    route_id: str
    path: str
    method: str
    template_name: str
    plan: DeferExecutionPlan
    origin: SourceOrigin

    def independent_keys(self) -> frozenset[str]:
        return self.plan.independent_keys()

    def coupled_key_pairs(self) -> frozenset[tuple[str, str]]:
        return self.plan.coupled_key_pairs()


@dataclass(frozen=True, slots=True)
class _SuspenseDeferDAG:
    """Frozen Suspense defer execution DAG published with runtime state."""

    routes: tuple[_SuspenseRoutePlan, ...] = ()
    keys: tuple[_DeferKeyNode, ...] = ()
    blocks: tuple[_DeferBlockNode, ...] = ()
    edges: tuple[_DeferEdge, ...] = ()

    def __post_init__(self) -> None:
        for label, values in (
            ("route plan", self.routes),
            ("defer key", self.keys),
            ("defer block", self.blocks),
            ("defer edge", self.edges),
        ):
            _reject_duplicate_ids(label, values)

    def plan_for_route(self, *, path: str, method: str = "GET") -> _SuspenseRoutePlan | None:
        route_id = stable_identity("route", method.upper(), path)
        return next((plan for plan in self.routes if plan.route_id == route_id), None)

    def plan_for_template(self, template_name: str) -> _SuspenseRoutePlan | None:
        return next(
            (plan for plan in self.routes if plan.template_name == template_name),
            None,
        )

    @property
    def topology_digest(self) -> str:
        receipt = (
            tuple(
                (
                    plan.id,
                    plan.route_id,
                    plan.path,
                    plan.method,
                    plan.template_name,
                    plan.plan.deferred_keys,
                    plan.plan.blocks,
                    plan.plan.pruned_ancestors,
                    plan.plan.edges,
                    plan.plan.explicit_blocks,
                )
                for plan in self.routes
            ),
            tuple((node.id, node.key, node.template_id, node.route_id) for node in self.keys),
            tuple((node.id, node.name, node.template_id, node.route_id) for node in self.blocks),
            tuple(
                (
                    edge.id,
                    edge.kind,
                    edge.source_id,
                    edge.destination_id,
                    edge.resolved,
                )
                for edge in self.edges
            ),
        )
        return hashlib.sha256(repr(receipt).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class _SuspenseCallFact:
    template: str
    context_keys: tuple[str, ...]
    defer_blocks: tuple[str, ...] | None
    origin: SourceOrigin


def _reject_duplicate_ids(label: str, values: tuple[Any, ...]) -> None:
    seen: set[str] = set()
    for value in values:
        identity = value.id
        if identity in seen:
            raise ConfigurationError(f"Duplicate suspense defer DAG {label} identity {identity!r}.")
        seen.add(identity)


def _dedent_handler_source(src: str) -> str:
    """Normalize indentation so ``ast.parse`` accepts nested method bodies."""
    lines = src.splitlines()
    if not lines:
        return src
    indents = [len(line) - len(line.lstrip(" \t")) for line in lines if line.strip()]
    if not indents:
        return src
    pad = min(indents)
    return "\n".join(line[pad:] if len(line) >= pad else line for line in lines)


def _string_const(node: ast.expr | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _string_tuple(node: ast.expr | None) -> tuple[str, ...] | None:
    if not isinstance(node, (ast.Tuple, ast.List)):
        return None
    values: list[str] = []
    for elt in node.elts:
        text = _string_const(elt)
        if text is None:
            return None
        values.append(text)
    return tuple(values)


def _call_name(node: ast.Call) -> str | None:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _handler_origin(route: Any) -> SourceOrigin:
    handler = getattr(route, "page_source_handler", None) or route.handler
    module = getattr(handler, "__module__", "<unknown>")
    qualname = getattr(handler, "__qualname__", getattr(handler, "__name__", "<handler>"))
    try:
        _, line = inspect.getsourcelines(handler)
    except TypeError, OSError:
        line = None
    return SourceOrigin("handler", f"{module}:{qualname}", line)


def _suspense_calls_from_handler(route: Any) -> tuple[_SuspenseCallFact, ...]:
    handler = getattr(route, "page_source_handler", None) or getattr(route, "handler", None)
    if handler is None:
        return ()
    try:
        src = inspect.getsource(handler)
    except TypeError, OSError:
        return ()
    try:
        tree = ast.parse(_dedent_handler_source(src))
    except SyntaxError:
        return ()
    origin = _handler_origin(route)
    facts: list[_SuspenseCallFact] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if _call_name(node) != "Suspense":
            continue
        template = _string_const(node.args[0]) if node.args else None
        if template is None:
            continue
        context_keys: list[str] = []
        defer_blocks: tuple[str, ...] | None = None
        for kw in node.keywords:
            if kw.arg is None:
                continue
            if kw.arg == "defer_blocks":
                defer_blocks = _string_tuple(kw.value)
                continue
            if kw.arg in _RESERVED_SUSPENSE_KW:
                continue
            context_keys.append(kw.arg)
        facts.append(
            _SuspenseCallFact(
                template=template,
                context_keys=tuple(sorted(set(context_keys))),
                defer_blocks=defer_blocks,
                origin=SourceOrigin(
                    "handler",
                    origin.identifier,
                    getattr(node, "lineno", None) or origin.line,
                ),
            )
        )
    return tuple(facts)


def _declared_defer_keys(source: str) -> set[str]:
    keys: set[str] = set()
    keys.update(_DEFER_PENDING_DECL.findall(source))
    keys.update(_DEFERRED_TEST.findall(source))
    return keys


def _depends_on_roots(env: Any, template_name: str) -> set[str] | None:
    try:
        template = env.get_template(template_name)
        metadata = template.block_metadata()
    except Exception:
        return None
    roots: set[str] = set()
    for block_meta in metadata.values():
        for dep_path in getattr(block_meta, "depends_on", ()):
            roots.add(dep_path.split(".")[0])
    return roots


def _resolve_deferred_keys(
    *,
    env: Any,
    template_name: str,
    template_source: str | None,
    context_keys: tuple[str, ...],
) -> frozenset[str]:
    """Choose compile-time defer keys for a Suspense call.

    Prefer template self-declarations (``is deferred`` / pending-set membership).
    Fall back to Suspense kwargs that appear in block ``depends_on`` roots so
    sync-only kwargs (``title=...``) are not treated as defer nodes.
    """
    declared = _declared_defer_keys(template_source or "")
    if declared:
        if context_keys:
            return frozenset(declared & set(context_keys)) or frozenset(declared)
        return frozenset(declared)
    roots = _depends_on_roots(env, template_name)
    if roots is None:
        return frozenset(context_keys)
    return frozenset(set(context_keys) & roots)


def _load_template_source(env: Any, template_name: str) -> str | None:
    loader = getattr(env, "loader", None)
    if loader is None:
        return None
    get_source = getattr(loader, "get_source", None)
    if not callable(get_source):
        return None
    try:
        source = get_source(env, template_name)
    except Exception:
        return None
    if isinstance(source, tuple):
        return source[0] if isinstance(source[0], str) else None
    return source if isinstance(source, str) else None


def _edge(
    kind: _DeferEdgeKind,
    source_id: str,
    destination_id: str,
    *,
    resolved: bool,
    origin: SourceOrigin,
) -> _DeferEdge:
    return _DeferEdge(
        id=stable_identity("defer_edge", kind, source_id, destination_id),
        kind=kind,
        source_id=source_id,
        destination_id=destination_id,
        resolved=resolved,
        origin=origin,
    )


def compile_suspense_defer_dag(
    *,
    router: Any,
    kida_env: Any | None,
    program: HypermediaProgram | None = None,
) -> _SuspenseDeferDAG:
    """Compile Suspense route defer execution DAGs at freeze.

    Discovers ``Suspense(...)`` calls on route handlers, plans each with the
    same discovery + ancestor-pruning algorithm as runtime, and publishes an
    immutable route-indexed DAG.
    """
    del program  # reserved for HypermediaProgram cross-links; DAG is sufficient for #949
    if kida_env is None:
        return _SuspenseDeferDAG()

    route_plans: list[_SuspenseRoutePlan] = []
    key_nodes: list[_DeferKeyNode] = []
    block_nodes: list[_DeferBlockNode] = []
    edges: list[_DeferEdge] = []

    for route in getattr(router, "routes", ()):
        facts = _suspense_calls_from_handler(route)
        if not facts:
            continue
        methods = sorted(getattr(route, "methods", ()) or ("GET",))
        for method in methods:
            route_id = stable_identity("route", method, route.path)
            for fact_index, fact in enumerate(facts):
                source = _load_template_source(kida_env, fact.template)
                deferred_keys = _resolve_deferred_keys(
                    env=kida_env,
                    template_name=fact.template,
                    template_source=source,
                    context_keys=fact.context_keys,
                )
                if not deferred_keys and fact.defer_blocks is None:
                    continue
                try:
                    plan = plan_defer_execution(
                        kida_env,
                        fact.template,
                        deferred_keys,
                        defer_blocks=fact.defer_blocks,
                    )
                except Exception:
                    # Template load / metadata failures stay soft at compile —
                    # runtime still fails loud on the request path.
                    _logger.debug(
                        "Skipping Suspense defer plan for %s (compile-time discovery failed)",
                        fact.template,
                        exc_info=True,
                    )
                    continue
                if not plan.blocks and fact.defer_blocks is None:
                    # Undiscoverable keys remain a runtime / #949 concern.
                    continue

                template_id = stable_identity("template", fact.template)
                plan_id = stable_identity(
                    "suspense_plan",
                    method,
                    route.path,
                    fact.template,
                    str(fact_index),
                )
                route_plans.append(
                    _SuspenseRoutePlan(
                        id=plan_id,
                        route_id=route_id,
                        path=route.path,
                        method=method,
                        template_name=fact.template,
                        plan=plan,
                        origin=fact.origin,
                    )
                )

                key_ids = {
                    key: stable_identity("defer_key", route_id, fact.template, key)
                    for key in plan.deferred_keys
                }
                block_ids = {
                    block: stable_identity("defer_block", route_id, fact.template, block)
                    for block in plan.blocks
                }
                key_nodes.extend(
                    _DeferKeyNode(
                        id=key_ids[key],
                        key=key,
                        template_id=template_id,
                        route_id=route_id,
                        origin=fact.origin,
                    )
                    for key in plan.deferred_keys
                )
                block_nodes.extend(
                    _DeferBlockNode(
                        id=block_ids[block],
                        name=block,
                        template_id=template_id,
                        route_id=route_id,
                        origin=fact.origin,
                    )
                    for block in plan.blocks
                )
                for edge in plan.edges:
                    if edge.kind == "feeds":
                        source_id = key_ids.get(edge.source)
                        dest_id = block_ids.get(edge.destination)
                        if source_id is None or dest_id is None:
                            continue
                        edges.append(
                            _edge(
                                "feeds",
                                source_id,
                                dest_id,
                                resolved=True,
                                origin=fact.origin,
                            )
                        )
                    elif edge.kind == "couples":
                        left = key_ids.get(edge.source)
                        right = key_ids.get(edge.destination)
                        if left is None or right is None:
                            continue
                        edges.append(
                            _edge(
                                "couples",
                                left,
                                right,
                                resolved=True,
                                origin=fact.origin,
                            )
                        )

    unique_keys = {node.id: node for node in key_nodes}
    unique_blocks = {node.id: node for node in block_nodes}
    unique_edges = {edge.id: edge for edge in edges}
    return _SuspenseDeferDAG(
        routes=tuple(sorted(route_plans, key=lambda plan: plan.id)),
        keys=tuple(sorted(unique_keys.values(), key=lambda node: node.id)),
        blocks=tuple(sorted(unique_blocks.values(), key=lambda node: node.id)),
        edges=tuple(sorted(unique_edges.values(), key=lambda edge: edge.id)),
    )
