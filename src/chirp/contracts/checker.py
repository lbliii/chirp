"""Hypermedia contracts checker orchestration."""

from typing import TYPE_CHECKING

from kida import Environment

from chirp.routing.router import _route_path_has_flask_syntax

from .declarations import FragmentContract, SSEContract
from .routes import (
    attr_to_method,
    build_route_index,
    collect_route_paths,
    find_matching_route,
)
from .rules_accessibility import check_accessibility
from .rules_forms import validate_form_contracts
from .rules_htmx import (
    check_hx_boost,
    check_hx_indicator_selectors,
    check_hx_target_selectors,
    check_selector_syntax,
)
from .rules_inline import check_inline_templates
from .rules_islands import check_island_mounts
from .rules_layout import check_layout_chains
from .rules_page_shell import check_page_shell_contracts
from .rules_route_contract import (
    check_context_provider_signatures,
    check_duplicate_routes,
    check_route_file_consistency,
    check_section_bindings,
    check_section_tab_hrefs,
    check_shell_mode_blocks,
)
from .rules_sse import (
    check_sse_connect_scope,
    check_sse_event_crossref,
    check_sse_self_swap,
)
from .rules_swap import check_swap_safety, collect_broad_targets
from .template_scan import (
    extract_fragment_island_ids,
    extract_ids_with_disinherit,
    extract_legacy_action_contracts,
    extract_static_ids,
    extract_targets_from_source,
    extract_template_references,
    extract_wizard_form_ids,
    load_template_sources,
)
from .types import CheckResult, ContractIssue, Severity

if TYPE_CHECKING:
    from chirp.app import App
    from chirp.app.state import ContractCheckSnapshot


def _route_prepass(
    router: object,
    kida_env: Environment | None,
    result: CheckResult,
) -> tuple[set[str], set[str]]:
    """Single pass over router.routes. Returns (referenced_templates, referenced_route_paths)."""
    referenced_templates: set[str] = set()
    referenced_route_paths: set[str] = set()
    routes = getattr(router, "routes", [])

    for route in routes:
        path = getattr(route, "path", "")
        if _route_path_has_flask_syntax(path):
            result.issues.append(
                ContractIssue(
                    severity=Severity.ERROR,
                    category="routing",
                    message=(
                        f"Route path uses '<param>' but Chirp expects '{{param}}'. "
                        f"Got: {path!r}. See docs/routing/routes.md"
                    ),
                    route=path,
                )
            )
        if getattr(route, "referenced", False):
            referenced_route_paths.add(path)
        template = getattr(route, "template", None)
        if template is not None:
            referenced_templates.add(template)
        contract = getattr(route.handler, "_chirp_contract", None)
        if contract is None:
            continue
        returns = getattr(contract, "returns", None)
        if isinstance(returns, FragmentContract):
            referenced_templates.add(returns.template)
            if kida_env is not None:
                try:
                    tmpl = kida_env.get_template(returns.template)
                    blocks = tmpl.block_metadata()
                    if returns.block not in blocks:
                        result.issues.append(
                            ContractIssue(
                                severity=Severity.ERROR,
                                category="fragment",
                                message=(
                                    f"Route '{path}' declares fragment "
                                    f"block '{returns.block}' but template "
                                    f"'{returns.template}' has no such block."
                                ),
                                route=path,
                                template=returns.template,
                            )
                        )
                except Exception:
                    result.issues.append(
                        ContractIssue(
                            severity=Severity.ERROR,
                            category="fragment",
                            message=(
                                f"Route '{path}' references template "
                                f"'{returns.template}' which could not be loaded."
                            ),
                            route=path,
                            template=returns.template,
                        )
                    )
        elif isinstance(returns, SSEContract) and kida_env is not None:
            for frag in returns.fragments:
                referenced_templates.add(frag.template)
                result.sse_fragments_validated += 1
                try:
                    tmpl = kida_env.get_template(frag.template)
                    blocks = tmpl.block_metadata()
                    if frag.block not in blocks:
                        result.issues.append(
                            ContractIssue(
                                severity=Severity.ERROR,
                                category="sse",
                                message=(
                                    f"SSE route '{path}' yields Fragment "
                                    f"'{frag.template}':'{frag.block}' "
                                    "but block doesn't exist."
                                ),
                                route=path,
                                template=frag.template,
                            )
                        )
                except Exception:
                    result.issues.append(
                        ContractIssue(
                            severity=Severity.ERROR,
                            category="sse",
                            message=(
                                f"SSE route '{path}' yields Fragment "
                                f"'{frag.template}' which could not be loaded."
                            ),
                            route=path,
                            template=frag.template,
                        )
                    )
    return referenced_templates, referenced_route_paths


def _build_snapshot(app: App) -> ContractCheckSnapshot:
    snapshot_builder = getattr(app, "_contract_check_snapshot", None)
    if callable(snapshot_builder):
        return snapshot_builder()
    app._ensure_frozen()
    router = app._router
    if router is None:
        msg = "No router available — app may not have routes."
        raise RuntimeError(msg)
    from chirp.app.state import ContractCheckSnapshot as _Snapshot

    return _Snapshot(
        router=router,
        kida_env=app._kida_env,
        layout_chains=getattr(app, "_discovered_layout_chains", []),
        page_route_paths=getattr(app, "_page_route_paths", set()),
        page_leaf_templates=getattr(app, "_page_leaf_templates", set()),
        page_templates=getattr(app, "_page_templates", set()),
        fragment_target_registry=app._mutable_state.fragment_target_registry,
        islands_contract_strict=app.config.islands_contract_strict,
        sections=getattr(app._mutable_state, "sections", {}),
        route_metas=getattr(app._mutable_state, "route_metas", {}),
        route_templates=getattr(app._mutable_state, "route_templates", {}),
        discovered_routes=getattr(app._mutable_state, "discovered_routes", []),
    )


def check_hypermedia_surface(app: App) -> CheckResult:
    """Validate app route/template contract consistency."""
    result = CheckResult()
    try:
        snapshot = _build_snapshot(app)
    except RuntimeError:
        result.issues.append(
            ContractIssue(
                severity=Severity.ERROR,
                category="setup",
                message="No router available — app may not have routes.",
            )
        )
        return result
    router = snapshot.router
    kida_env = snapshot.kida_env

    route_paths = collect_route_paths(router)
    result.routes_checked = len(route_paths)

    referenced_templates_from_routes, referenced_route_paths = _route_prepass(
        router, kida_env, result
    )
    check_inline_templates(router, result)

    if kida_env is not None and kida_env.loader is not None:
        template_sources = load_template_sources(kida_env)
        result.templates_scanned = len(template_sources)
        referenced_paths: set[str] = set()
        static_routes, parametric_routes = build_route_index(route_paths)

        all_ids: set[str] = set()
        static_ids: set[str] = set()
        ids_with_disinherit: set[str] = set()
        referenced_templates_from_sources: set[str] = set()

        for template_name, source in template_sources.items():
            if template_name.startswith("chirpui/"):
                continue
            for legacy_action in sorted(extract_legacy_action_contracts(source)):
                result.issues.append(
                    ContractIssue(
                        severity=Severity.WARNING,
                        category="template_contract",
                        message=(
                            f"'action=\"{legacy_action}\"' looks like a legacy component contract, "
                            "not a URL. Replace it with href=, hx-*, confirm_url=, or a real "
                            "form action path."
                        ),
                        template=template_name,
                    )
                )
            targets = extract_targets_from_source(source)
            result.targets_found += len(targets)
            for attr_name, url, method_override in targets:
                if attr_name == "action" and not url.startswith("/"):
                    continue
                method = attr_to_method(attr_name, method_override)
                match = find_matching_route(url, static_routes, parametric_routes)
                if match is not None:
                    matched_route, methods = match
                    referenced_paths.add(matched_route)
                    if method not in methods:
                        result.issues.append(
                            ContractIssue(
                                severity=Severity.ERROR,
                                category="method",
                                message=(
                                    f"'{attr_name}=\"{url}\"' uses {method} "
                                    f"but route '{matched_route}' only allows "
                                    f"{', '.join(sorted(methods))}."
                                ),
                                template=template_name,
                                route=matched_route,
                            )
                        )
                else:
                    result.issues.append(
                        ContractIssue(
                            severity=Severity.ERROR,
                            category="target",
                            message=f"'{attr_name}=\"{url}\"' has no matching route.",
                            template=template_name,
                        )
                    )
            s = extract_static_ids(source)
            static_ids.update(s)
            all_ids.update(s)
            all_ids.update(extract_fragment_island_ids(source))
            all_ids.update(extract_wizard_form_ids(source))
            ids_with_disinherit.update(extract_ids_with_disinherit(source))
            referenced_templates_from_sources.update(extract_template_references(source))

        hx_target_issues, hx_validated = check_hx_target_selectors(template_sources, all_ids)
        result.hx_targets_validated = hx_validated
        result.issues.extend(hx_target_issues)
        result.issues.extend(check_hx_indicator_selectors(template_sources, all_ids))
        result.issues.extend(check_selector_syntax(template_sources))
        result.issues.extend(check_hx_boost(template_sources))
        result.issues.extend(
            check_swap_safety(
                template_sources,
                all_ids=static_ids,
                all_ids_with_disinherit=ids_with_disinherit,
            )
        )
        result.issues.extend(check_sse_self_swap(template_sources))
        broad_targets = collect_broad_targets(template_sources)
        result.issues.extend(check_sse_connect_scope(template_sources, broad_targets))
        result.issues.extend(check_sse_event_crossref(template_sources, router))
        result.issues.extend(check_layout_chains(snapshot.layout_chains, template_sources))
        result.issues.extend(
            check_page_shell_contracts(
                snapshot.page_leaf_templates,
                snapshot.fragment_target_registry,
                kida_env,
            )
        )
        result.issues.extend(check_section_bindings(snapshot.route_metas, snapshot.sections))
        result.issues.extend(
            check_shell_mode_blocks(
                snapshot.route_metas,
                snapshot.route_templates,
                snapshot.fragment_target_registry,
                kida_env,
            )
        )
        action_route_paths = {
            r.url_path
            for r in getattr(snapshot, "discovered_routes", [])
            if getattr(r, "kind", None) == "action"
        }
        result.issues.extend(
            check_route_file_consistency(
                snapshot.route_metas, snapshot.page_route_paths, action_route_paths
            )
        )
        result.issues.extend(check_duplicate_routes(getattr(snapshot, "discovered_routes", [])))
        result.issues.extend(check_section_tab_hrefs(snapshot.sections, snapshot.page_route_paths))
        providers = getattr(app._mutable_state, "providers", None)
        result.issues.extend(
            check_context_provider_signatures(
                getattr(snapshot, "discovered_routes", []),
                providers,
            )
        )
        result.issues.extend(
            check_island_mounts(template_sources, strict=snapshot.islands_contract_strict)
        )
        for template_name, source in template_sources.items():
            if template_name.startswith(("chirp/", "chirpui/")):
                continue
            result.issues.extend(check_accessibility(source, template_name))

        result.issues.extend(validate_form_contracts(result, router, template_sources))

        page_route_paths = snapshot.page_route_paths
        for route_path in route_paths:
            if route_path in referenced_paths or route_path == "/":
                continue
            if route_path in page_route_paths:
                continue
            if route_path in referenced_route_paths:
                continue
            # Skip param-based routes: static analysis can't prove dynamic URLs reference them
            if "{" in route_path:
                continue
            result.issues.append(
                ContractIssue(
                    severity=Severity.INFO,
                    category="orphan",
                    message=f"Route '{route_path}' is not referenced from any template.",
                    route=route_path,
                )
            )

        all_template_names = set(template_sources)
        referenced_templates = (
            referenced_templates_from_routes
            | referenced_templates_from_sources
            | snapshot.page_templates
        )

        dead = sorted(all_template_names - referenced_templates)
        for template_name in dead:
            basename = template_name.rsplit("/", 1)[-1]
            if basename.startswith("_"):
                continue
            if template_name.startswith(("chirp/", "chirpui/", "themes/")):
                continue
            result.dead_templates_found += 1
            result.issues.append(
                ContractIssue(
                    severity=Severity.INFO,
                    category="dead",
                    message=(
                        f"Template '{template_name}' is not referenced by any route or template."
                    ),
                    template=template_name,
                )
            )

    if kida_env is not None:
        for route in router.routes:
            route_contract = getattr(route.handler, "_chirp_contract", None)
            if route_contract is None or not isinstance(route_contract.returns, FragmentContract):
                continue
            fragment_contract = route_contract.returns
            try:
                template = kida_env.get_template(fragment_contract.template)
                blocks = template.block_metadata()
                if fragment_contract.block not in blocks:
                    continue
                block_deps = blocks[fragment_contract.block].depends_on
                full_deps = template.depends_on()
                block_vars = {path.split(".")[0] for path in block_deps}
                full_vars = {path.split(".")[0] for path in full_deps}
                extra = sorted(full_vars - block_vars)
                env_globals = set(kida_env.globals) if hasattr(kida_env, "globals") else set()
                extra = [value for value in extra if value not in env_globals]
                if extra:
                    result.page_context_warnings += 1
                    result.issues.append(
                        ContractIssue(
                            severity=Severity.WARNING,
                            category="page_context",
                            message=(
                                f"Route '{route.path}' uses block '{fragment_contract.block}' "
                                f"but full-page render of '{fragment_contract.template}' also "
                                f"needs: {', '.join(extra)}. Pass defaults in "
                                "your Page() call to avoid runtime errors."
                            ),
                            route=route.path,
                            template=fragment_contract.template,
                        )
                    )
            except Exception:
                pass

    if kida_env is not None:
        validate_fn = getattr(kida_env, "validate_calls", None)
        if callable(validate_fn):
            for issue in validate_fn():
                result.component_calls_validated += 1
                result.issues.append(
                    ContractIssue(
                        severity=Severity.ERROR if issue.is_error else Severity.WARNING,
                        category="component",
                        message=issue.message,
                        template=getattr(issue, "template", None),
                    )
                )

    return result
