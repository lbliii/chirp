"""Route directory contract validation."""

from kida import Environment

from chirp.pages.types import RouteMeta
from chirp.templating.fragment_target_registry import FragmentTargetRegistry

from .types import ContractIssue, Severity


def check_section_bindings(
    route_metas: dict[str, RouteMeta | None],
    sections: dict[str, object],
) -> list[ContractIssue]:
    """Warn if RouteMeta.section references unknown section."""
    issues: list[ContractIssue] = []
    for path, meta in route_metas.items():
        if meta is None or meta.section is None:
            continue
        if meta.section not in sections:
            issues.append(
                ContractIssue(
                    severity=Severity.WARNING,
                    category="route_contract",
                    message=(
                        f"Route '{path}' references unknown section '{meta.section}'. "
                        "Register the section with app.register_section() before mount_pages()."
                    ),
                    route=path,
                )
            )
    return issues


def check_shell_mode_blocks(
    route_metas: dict[str, RouteMeta | None],
    route_templates: dict[str, str],
    fragment_target_registry: FragmentTargetRegistry,
    kida_env: Environment | None,
) -> list[ContractIssue]:
    """Error if shell_mode='tabbed' but template lacks required blocks."""
    issues: list[ContractIssue] = []
    if kida_env is None:
        return issues
    required = fragment_target_registry.required_fragment_blocks
    if not required:
        return issues

    for path, meta in route_metas.items():
        if meta is None or meta.shell_mode != "tabbed":
            continue
        template_name = route_templates.get(path)
        if not template_name:
            continue
        try:
            template = kida_env.get_template(template_name)
            blocks = template.block_metadata()
        except Exception:
            continue
        missing = [b for b in required if b not in blocks]
        if missing:
            issues.append(
                ContractIssue(
                    severity=Severity.ERROR,
                    category="route_contract",
                    message=(
                        f"Route '{path}' has shell_mode='tabbed' but template "
                        f"'{template_name}' lacks required block(s): {', '.join(missing)}."
                    ),
                    route=path,
                    template=template_name,
                )
            )
    return issues


def check_route_file_consistency(
    route_metas: dict[str, RouteMeta | None],
    page_route_paths: set[str],
) -> list[ContractIssue]:
    """Info-level for page routes without _meta.py."""
    return [
        ContractIssue(
            severity=Severity.INFO,
            category="route_contract",
            message=(
                f"Route '{path}' has no _meta.py. Consider adding one for "
                "title, section, breadcrumb_label, etc."
            ),
            route=path,
        )
        for path in page_route_paths
        if path not in route_metas or route_metas[path] is None
    ]
