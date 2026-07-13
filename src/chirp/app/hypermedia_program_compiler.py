"""Compiler for the internal immutable hypermedia application model."""

from __future__ import annotations

import inspect
from typing import Any

from .hypermedia_program import (
    BlockNode,
    EnhancementEdge,
    EnhancementNode,
    HypermediaProgram,
    Provenance,
    RouteNode,
    SourceOrigin,
    TargetNode,
    TemplateDeclaration,
    TemplateNode,
    TransitionEdge,
    TransitionKind,
    stable_identity,
)

_TEMPLATE_SUFFIXES = (".html", ".htm", ".jinja", ".j2")


def _handler_origin(route: Any) -> SourceOrigin:
    handler = getattr(route, "page_source_handler", None) or route.handler
    module = getattr(handler, "__module__", "<unknown>")
    qualname = getattr(handler, "__qualname__", getattr(handler, "__name__", "<handler>"))
    try:
        _, line = inspect.getsourcelines(handler)
    except TypeError, OSError:
        line = None
    return SourceOrigin("handler", f"{module}:{qualname}", line)


def _route_template_references(route: Any) -> tuple[tuple[str, str | None], ...]:
    references: set[tuple[str, str | None]] = set()
    if route.template:
        references.add((route.template, None))
    contract = getattr(route.handler, "_chirp_contract", None)
    returns = getattr(contract, "returns", None)
    template = getattr(returns, "template", None)
    if isinstance(template, str):
        references.add((template, getattr(returns, "block", None)))
    for fragment in getattr(returns, "fragments", ()):
        fragment_template = getattr(fragment, "template", None)
        if isinstance(fragment_template, str):
            references.add((fragment_template, getattr(fragment, "block", None)))
    form = getattr(contract, "form", None)
    form_template = getattr(form, "template", None)
    if isinstance(form_template, str):
        references.add((form_template, getattr(form, "block", None)))
    return tuple(sorted(references))


def _normalize_declarations(
    declarations: list[TemplateDeclaration],
) -> tuple[TemplateDeclaration, ...]:
    """Return exact declarations once in deterministic semantic order."""
    return tuple(
        sorted(
            set(declarations),
            key=lambda declaration: (
                declaration.template,
                declaration.blocks,
                declaration.origin.identifier,
                declaration.origin.line if declaration.origin.line is not None else -1,
            ),
        )
    )


def _reachable_template_names(
    router: Any,
    page_templates: set[str],
    declarations: tuple[TemplateDeclaration, ...],
) -> tuple[str, ...]:
    """Collect templates proven reachable from registration and route contracts.

    Loader-wide inventory remains in the dead-template checker until that rule
    migrates. Eagerly parsing every bundled template would penalize apps that do
    not render templates and would make this graph a second source of truth.
    """
    names = set(page_templates)
    for route in router.routes:
        names.update(template for template, _block in _route_template_references(route))
    inferred = {
        name for name in names if isinstance(name, str) and name.endswith(_TEMPLATE_SUFFIXES)
    }
    inferred.update(declaration.template for declaration in declarations)
    return tuple(sorted(inferred))


def _compile_templates(
    names: tuple[str, ...],
    kida_env: Any,
    page_templates: set[str],
    page_leaf_templates: set[str],
) -> tuple[
    tuple[TemplateNode, ...],
    tuple[BlockNode, ...],
    tuple[EnhancementNode, ...],
    tuple[EnhancementEdge, ...],
]:
    templates: list[TemplateNode] = []
    blocks: list[BlockNode] = []
    enhancements: list[EnhancementNode] = []
    enhancement_edges: list[EnhancementEdge] = []
    for name in names:
        template_id = stable_identity("template", name)
        block_names: tuple[str, ...] = ()
        extends: str | None = None
        load_error: str | None = None
        try:
            template = kida_env.get_template(name)
            metadata = template.template_metadata()
            block_names = tuple(sorted(metadata.blocks))
            extended = getattr(metadata, "extends", None)
            extends = extended if isinstance(extended, str) else None

            block_ids = {stable_identity("block", name, block) for block in block_names}
            for block_name in block_names:
                block_metadata = metadata.blocks[block_name]
                enhancement = block_metadata.get_modifier("enhancement")
                if enhancement is None:
                    continue
                fallback = block_metadata.get_modifier("fallback")
                block_id = stable_identity("block", name, block_name)
                origin = SourceOrigin("template", f"{name}:{block_name}", enhancement.lineno)
                enhancements.append(
                    EnhancementNode(
                        id=stable_identity("enhancement", name, block_name),
                        template_id=template_id,
                        block_id=block_id,
                        capability=enhancement.value,
                        fallback=fallback.value if fallback is not None else None,
                        fallback_declared=fallback is not None,
                        origin=origin,
                    )
                )
                if fallback is not None and isinstance(fallback.value, str):
                    fallback_block_id = stable_identity("block", name, fallback.value)
                    enhancement_edges.append(
                        EnhancementEdge(
                            id=stable_identity("enhancement_edge", block_id, fallback_block_id),
                            enhanced_block_id=block_id,
                            fallback_block_id=fallback_block_id,
                            resolved=fallback_block_id in block_ids,
                            origin=origin,
                        )
                    )
        except Exception as exc:
            load_error = f"{type(exc).__name__}: {exc}"
        origin = SourceOrigin("template", name)
        block_ids = tuple(stable_identity("block", name, block) for block in block_names)
        templates.append(
            TemplateNode(
                id=template_id,
                name=name,
                block_ids=block_ids,
                extends=extends,
                is_page=name in page_templates,
                is_page_leaf=name in page_leaf_templates,
                origin=origin,
                load_error=load_error,
            )
        )
        blocks.extend(
            BlockNode(stable_identity("block", name, block), template_id, block, origin)
            for block in block_names
        )
    return (
        tuple(templates),
        tuple(sorted(blocks, key=lambda node: node.id)),
        tuple(sorted(enhancements, key=lambda node: node.id)),
        tuple(sorted(enhancement_edges, key=lambda edge: edge.id)),
    )


def _compile_routes(router: Any) -> tuple[RouteNode, ...]:
    nodes: list[RouteNode] = []
    for route in router.routes:
        references = _route_template_references(route)
        template_ids = tuple(
            sorted({stable_identity("template", template) for template, _ in references})
        )
        origin = _handler_origin(route)
        nodes.extend(
            RouteNode(
                id=stable_identity("route", method, route.path),
                path=route.path,
                method=method,
                name=route.name,
                template_ids=template_ids,
                origin=origin,
            )
            for method in sorted(route.methods)
        )
    return tuple(sorted(nodes, key=lambda node: node.id))


def _compile_targets(registry: Any) -> tuple[TargetNode, ...]:
    nodes: list[TargetNode] = []
    for target_id in sorted(registry.registered_targets):
        config = registry.get(target_id)
        if config is None:
            continue
        identifier = f"contract:{config.contract_name}" if config.contract_name else target_id
        nodes.append(
            TargetNode(
                id=stable_identity("target", target_id),
                target_id=target_id,
                fragment_block=config.fragment_block,
                required=config.required,
                contract_name=config.contract_name,
                origin=SourceOrigin("registry", identifier),
            )
        )
    return tuple(nodes)


def _edge(
    kind: TransitionKind,
    source_id: str,
    destination_id: str,
    *,
    resolved: bool,
    origin: SourceOrigin,
    provenance: Provenance,
) -> TransitionEdge:
    return TransitionEdge(
        id=stable_identity("transition", kind, source_id, destination_id),
        kind=kind,
        source_id=source_id,
        destination_id=destination_id,
        resolved=resolved,
        origin=origin,
        provenance=provenance,
    )


def _compile_route_transitions(
    router: Any,
    routes: tuple[RouteNode, ...],
    templates: tuple[TemplateNode, ...],
    blocks: tuple[BlockNode, ...],
) -> list[TransitionEdge]:
    template_by_id = {node.id: node for node in templates}
    block_ids = {node.id for node in blocks}
    route_by_key = {(node.method, node.path): node for node in routes}
    edges: list[TransitionEdge] = []
    for route in router.routes:
        for method in sorted(route.methods):
            route_node = route_by_key[(method, route.path)]
            origin = route_node.origin
            for template_name, block_name in _route_template_references(route):
                template_id = stable_identity("template", template_name)
                template = template_by_id[template_id]
                edge = _edge(
                    "route_template",
                    route_node.id,
                    template_id,
                    resolved=template.load_error is None,
                    origin=origin,
                    provenance="declared",
                )
                edges.append(edge)
                if block_name:
                    block_id = stable_identity("block", template_name, block_name)
                    edges.append(
                        _edge(
                            "route_block",
                            route_node.id,
                            block_id,
                            resolved=block_id in block_ids,
                            origin=origin,
                            provenance="declared",
                        )
                    )
    return edges


def _compile_template_transitions(
    templates: tuple[TemplateNode, ...],
    blocks: tuple[BlockNode, ...],
) -> list[TransitionEdge]:
    template_by_id = {node.id: node for node in templates}
    return [
        _edge(
            "template_block",
            block.template_id,
            block.id,
            resolved=True,
            origin=template_by_id[block.template_id].origin,
            provenance="inferred",
        )
        for block in blocks
    ]


def _compile_target_transitions(
    templates: tuple[TemplateNode, ...],
    blocks: tuple[BlockNode, ...],
    targets: tuple[TargetNode, ...],
) -> list[TransitionEdge]:
    block_ids = {node.id for node in blocks}
    page_templates = tuple(node for node in templates if node.is_page_leaf)
    return [
        _edge(
            "target_block",
            target.id,
            stable_identity("block", template.name, target.fragment_block),
            resolved=stable_identity("block", template.name, target.fragment_block) in block_ids,
            origin=target.origin,
            provenance="declared",
        )
        for target in targets
        for template in page_templates
    ]


def _compile_transitions(
    router: Any,
    routes: tuple[RouteNode, ...],
    templates: tuple[TemplateNode, ...],
    blocks: tuple[BlockNode, ...],
    targets: tuple[TargetNode, ...],
) -> tuple[TransitionEdge, ...]:
    compiled = [
        *_compile_route_transitions(router, routes, templates, blocks),
        *_compile_template_transitions(templates, blocks),
        *_compile_target_transitions(templates, blocks, targets),
    ]
    edges: dict[str, TransitionEdge] = {}
    for edge in compiled:
        edges[edge.id] = edge
    return tuple(sorted(edges.values(), key=lambda edge: edge.id))


def compile_hypermedia_program(
    *,
    router: Any,
    kida_env: Any,
    page_templates: set[str],
    page_leaf_templates: set[str],
    fragment_target_registry: Any,
    template_declarations: list[TemplateDeclaration],
) -> HypermediaProgram:
    """Compile existing runtime inputs into one immutable internal model."""
    routes = _compile_routes(router)
    declarations = _normalize_declarations(template_declarations)
    names = _reachable_template_names(router, page_templates, declarations)
    templates, blocks, enhancements, enhancement_edges = _compile_templates(
        names,
        kida_env,
        page_templates,
        page_leaf_templates,
    )
    targets = _compile_targets(fragment_target_registry)
    transitions = _compile_transitions(router, routes, templates, blocks, targets)
    return HypermediaProgram(
        routes=routes,
        templates=templates,
        blocks=blocks,
        targets=targets,
        enhancements=enhancements,
        enhancement_edges=enhancement_edges,
        transitions=transitions,
        template_declarations=declarations,
    )
