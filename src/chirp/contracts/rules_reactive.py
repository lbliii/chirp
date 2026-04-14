"""Reactive bus contract checks.

Validates DependencyIndex configuration at app.check() time:
- Block references point to real template blocks
- Derivation graph is a DAG (no cycles)
"""


from typing import TYPE_CHECKING

from .types import ContractIssue, Severity

if TYPE_CHECKING:
    from kida import Environment

    from chirp.pages.reactive.index import DependencyIndex


def check_reactive_block_existence(
    dep_index: DependencyIndex,
    env: Environment,
) -> list[ContractIssue]:
    """Verify every BlockRef in the index references a real template block."""
    issues: list[ContractIssue] = []
    checked: set[tuple[str, str]] = set()

    for refs in dep_index._path_to_blocks.values():
        for ref in refs:
            key = (ref.template_name, ref.block_name)
            if key in checked:
                continue
            checked.add(key)
            try:
                template = env.get_template(ref.template_name)
                blocks = template.block_metadata()
                if ref.block_name not in blocks:
                    issues.append(
                        ContractIssue(
                            severity=Severity.ERROR,
                            category="reactive_block",
                            message=(
                                f"DependencyIndex references block '{ref.block_name}' "
                                f"in template '{ref.template_name}', but no such block exists. "
                                f"Available: {', '.join(sorted(blocks)) or '(none)'}."
                            ),
                            template=ref.template_name,
                        )
                    )
            except Exception:
                issues.append(
                    ContractIssue(
                        severity=Severity.ERROR,
                        category="reactive_block",
                        message=(
                            f"DependencyIndex references template '{ref.template_name}' "
                            "which could not be loaded."
                        ),
                        template=ref.template_name,
                    )
                )
    return issues


def check_reactive_derivation_dag(
    dep_index: DependencyIndex,
) -> list[ContractIssue]:
    """Detect cycles in the derivation graph.

    Cycles are handled safely at runtime (BFS visited set), but always
    indicate a configuration error.  Surfacing at check time is better
    than silent infinite-expansion prevention at runtime.
    """
    issues: list[ContractIssue] = []
    graph = dep_index._source_to_derived

    if not graph:
        return issues

    # Collect all nodes
    white, gray, black = 0, 1, 2
    color: dict[str, int] = {}
    for source, targets in graph.items():
        color.setdefault(source, white)
        for t in targets:
            color.setdefault(t, white)

    reported_cycles: set[frozenset[str]] = set()

    def dfs(node: str, path: list[str]) -> None:
        color[node] = gray
        path.append(node)
        for neighbor in graph.get(node, []):
            if color.get(neighbor, white) == gray:
                cycle_start = path.index(neighbor)
                cycle = [*path[cycle_start:], neighbor]
                cycle_key = frozenset(cycle)
                if cycle_key not in reported_cycles:
                    reported_cycles.add(cycle_key)
                    issues.append(
                        ContractIssue(
                            severity=Severity.WARNING,
                            category="reactive_cycle",
                            message=(
                                f"Derivation cycle detected: {' -> '.join(cycle)}. "
                                "Cycles are handled safely at runtime but indicate "
                                "a configuration error."
                            ),
                        )
                    )
            elif color.get(neighbor, white) == white:
                dfs(neighbor, path)
        path.pop()
        color[node] = black

    for node in list(color):
        if color[node] == white:
            dfs(node, [])

    return issues
