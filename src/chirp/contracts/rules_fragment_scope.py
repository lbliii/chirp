"""Fragment/block render scope contract checks."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .types import ContractIssue, Severity

if TYPE_CHECKING:
    from kida import Environment


@dataclass(frozen=True, slots=True)
class _ScopedBinding:
    name: str
    owner_block: str
    kind: str
    lineno: int | None


def _node_lineno(node: object) -> int | None:
    value = getattr(node, "lineno", None)
    return value if isinstance(value, int) else None


def _extract_name_targets(expr: object) -> frozenset[str]:
    """Return names assigned by a Kida target expression."""
    if type(expr).__name__ == "Name":
        name = getattr(expr, "name", None)
        return frozenset({name}) if isinstance(name, str) else frozenset()
    names: set[str] = set()
    for item in getattr(expr, "items", ()) or ():
        names.update(_extract_name_targets(item))
    return frozenset(names)


def _binding_names(node: object) -> frozenset[tuple[str, str]]:
    """Return ``(name, kind)`` pairs introduced by one Kida AST node."""
    node_type = type(node).__name__
    if node_type == "FromImport":
        imported: set[tuple[str, str]] = set()
        for original, alias in getattr(node, "names", ()) or ():
            bound = alias or original
            if isinstance(bound, str):
                imported.add((bound, "import"))
        return frozenset(imported)
    if node_type == "Import":
        target = getattr(node, "target", None)
        return frozenset({(target, "import")}) if isinstance(target, str) else frozenset()
    if node_type == "Set":
        return frozenset(
            (name, "set") for name in _extract_name_targets(getattr(node, "target", None))
        )
    if node_type in {"Let", "Export"}:
        return frozenset(
            (name, node_type.lower()) for name in _extract_name_targets(getattr(node, "name", None))
        )
    if node_type == "Capture":
        name = getattr(node, "name", None)
        return frozenset({(name, "capture")}) if isinstance(name, str) else frozenset()
    if node_type in {"Def", "Region"}:
        name = getattr(node, "name", None)
        return frozenset({(name, node_type.lower())}) if isinstance(name, str) else frozenset()
    return frozenset()


def _direct_bindings(nodes: Sequence[object], owner_block: str) -> frozenset[_ScopedBinding]:
    bindings: set[_ScopedBinding] = set()
    for node in nodes:
        for name, kind in _binding_names(node):
            bindings.add(
                _ScopedBinding(
                    name=name,
                    owner_block=owner_block,
                    kind=kind,
                    lineno=_node_lineno(node),
                )
            )
    return frozenset(bindings)


def _top_level_bindings(ast: object) -> frozenset[str]:
    return frozenset(
        binding.name for binding in _direct_bindings(getattr(ast, "body", ()) or (), "<top>")
    )


def _top_level_dependency_names(dependencies: Iterable[str]) -> frozenset[str]:
    return frozenset(dep.split(".", 1)[0] for dep in dependencies)


def _child_sequences(node: object) -> Iterable[Sequence[object]]:
    for attr in ("body", "else_", "empty"):
        children = getattr(node, attr, None)
        if isinstance(children, (list, tuple)):
            yield children
    elif_ = getattr(node, "elif_", None)
    if isinstance(elif_, (list, tuple)):
        for _test, body in elif_:
            if isinstance(body, (list, tuple)):
                yield body
    cases = getattr(node, "cases", None)
    if isinstance(cases, (list, tuple)):
        for _pattern, _guard, body in cases:
            if isinstance(body, (list, tuple)):
                yield body


def _check_nodes(
    *,
    nodes: Sequence[object],
    template_name: str,
    block_dependencies: Mapping[str, frozenset[str]],
    ancestor_bindings: tuple[_ScopedBinding, ...],
    top_level_names: frozenset[str],
    env_global_names: frozenset[str],
) -> list[ContractIssue]:
    issues: list[ContractIssue] = []
    for node in nodes:
        if type(node).__name__ == "Block":
            block_name = getattr(node, "name", None)
            body = getattr(node, "body", ()) or ()
            if not isinstance(block_name, str) or not isinstance(body, (list, tuple)):
                continue

            deps = block_dependencies.get(block_name, frozenset())
            dep_names = _top_level_dependency_names(deps)
            self_names = frozenset(binding.name for binding in _direct_bindings(body, block_name))
            hidden = [
                binding
                for binding in ancestor_bindings
                if binding.name in dep_names
                and binding.name not in self_names
                and binding.name not in top_level_names
                and binding.name not in env_global_names
            ]
            if hidden:
                names = ", ".join(sorted({binding.name for binding in hidden}))
                owner_names = ", ".join(
                    sorted({f"block '{binding.owner_block}'" for binding in hidden})
                )
                issues.append(
                    ContractIssue(
                        severity=Severity.WARNING,
                        category="fragment_scope",
                        message=(
                            f"Fragment block '{block_name}' references {names}, but "
                            f"{names} is defined inside {owner_names}. Move imports or "
                            "bindings required by fragment blocks to template top level."
                        ),
                        template=template_name,
                        details=(
                            f"Rendering '{block_name}' directly with render_block() or "
                            "the block-fetch dispatcher skips ancestor block local scope."
                        ),
                    )
                )

            next_ancestors = ancestor_bindings + tuple(_direct_bindings(body, block_name))
            issues.extend(
                _check_nodes(
                    nodes=body,
                    template_name=template_name,
                    block_dependencies=block_dependencies,
                    ancestor_bindings=next_ancestors,
                    top_level_names=top_level_names,
                    env_global_names=env_global_names,
                )
            )
            continue

        for children in _child_sequences(node):
            issues.extend(
                _check_nodes(
                    nodes=children,
                    template_name=template_name,
                    block_dependencies=block_dependencies,
                    ancestor_bindings=ancestor_bindings,
                    top_level_names=top_level_names,
                    env_global_names=env_global_names,
                )
            )
    return issues


def check_fragment_block_scope(
    template_sources: Mapping[str, str],
    kida_env: Environment | None,
) -> list[ContractIssue]:
    """Warn when fragment blocks depend on ancestor-block local bindings."""
    if kida_env is None:
        return []
    env_global_names = frozenset(kida_env.globals) if hasattr(kida_env, "globals") else frozenset()
    issues: list[ContractIssue] = []
    for template_name in template_sources:
        if template_name.startswith(("chirp/", "chirpui/")):
            continue
        try:
            template = kida_env.get_template(template_name)
            ast = getattr(template, "_optimized_ast", None)
            if ast is None:
                continue
            block_dependencies = {
                block_name: frozenset(getattr(meta, "depends_on", ()))
                for block_name, meta in template.block_metadata().items()
            }
        except Exception:
            continue
        issues.extend(
            _check_nodes(
                nodes=getattr(ast, "body", ()) or (),
                template_name=template_name,
                block_dependencies=block_dependencies,
                ancestor_bindings=(),
                top_level_names=_top_level_bindings(ast),
                env_global_names=env_global_names,
            )
        )
    return issues
