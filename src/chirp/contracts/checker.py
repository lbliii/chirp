"""Hypermedia contracts checker orchestration."""

from typing import TYPE_CHECKING

from chirp.routing.router import _route_path_has_flask_syntax

from .declarations import FragmentContract, SSEContract
from .routes import attr_to_method, collect_route_paths, path_matches_route
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
from .rules_sse import (
    check_sse_connect_scope,
    check_sse_event_crossref,
    check_sse_self_swap,
)
from .rules_swap import check_swap_safety, collect_broad_targets
from .template_scan import (
    extract_legacy_action_contracts,
    extract_fragment_island_ids,
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
        page_templates=getattr(app, "_page_templates", set()),
        islands_contract_strict=app.config.islands_contract_strict,
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

    for route in router.routes:
        if _route_path_has_flask_syntax(route.path):
            result.issues.append(
                ContractIssue(
                    severity=Severity.ERROR,
                    category="routing",
                    message=(
                        f"Route path uses '<param>' but Chirp expects '{{param}}'. "
                        f"Got: {route.path!r}. See docs/routing/routes.md"
                    ),
                    route=route.path,
                )
            )

    for route in router.routes:
        contract = getattr(route.handler, "_chirp_contract", None)
        if contract is None:
            continue
        if isinstance(contract.returns, FragmentContract):
            fragment_contract = contract.returns
            if kida_env is not None:
                try:
                    template = kida_env.get_template(fragment_contract.template)
                    blocks = template.block_metadata()
                    if fragment_contract.block not in blocks:
                        result.issues.append(
                            ContractIssue(
                                severity=Severity.ERROR,
                                category="fragment",
                                message=(
                                    f"Route '{route.path}' declares fragment "
                                    f"block '{fragment_contract.block}' but template "
                                    f"'{fragment_contract.template}' has no such block."
                                ),
                                route=route.path,
                                template=fragment_contract.template,
                            )
                        )
                except Exception:
                    result.issues.append(
                        ContractIssue(
                            severity=Severity.ERROR,
                            category="fragment",
                            message=(
                                f"Route '{route.path}' references template "
                                f"'{fragment_contract.template}' which could not be loaded."
                            ),
                            route=route.path,
                            template=fragment_contract.template,
                        )
                    )
        elif isinstance(contract.returns, SSEContract) and kida_env is not None:
            for fragment_contract in contract.returns.fragments:
                result.sse_fragments_validated += 1
                try:
                    template = kida_env.get_template(fragment_contract.template)
                    blocks = template.block_metadata()
                    if fragment_contract.block not in blocks:
                        result.issues.append(
                            ContractIssue(
                                severity=Severity.ERROR,
                                category="sse",
                                message=(
                                    f"SSE route '{route.path}' yields Fragment "
                                    f"'{fragment_contract.template}':'{fragment_contract.block}' "
                                    "but block doesn't exist."
                                ),
                                route=route.path,
                                template=fragment_contract.template,
                            )
                        )
                except Exception:
                    result.issues.append(
                        ContractIssue(
                            severity=Severity.ERROR,
                            category="sse",
                            message=(
                                f"SSE route '{route.path}' yields Fragment "
                                f"'{fragment_contract.template}' which could not be loaded."
                            ),
                            route=route.path,
                            template=fragment_contract.template,
                        )
                    )

    check_inline_templates(router, result)

    if kida_env is not None and kida_env.loader is not None:
        template_sources = load_template_sources(kida_env)
        result.templates_scanned = len(template_sources)
        referenced_paths: set[str] = set()

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
                matched = False
                for route_path, methods in route_paths.items():
                    if path_matches_route(url, route_path):
                        referenced_paths.add(route_path)
                        if method not in methods:
                            result.issues.append(
                                ContractIssue(
                                    severity=Severity.ERROR,
                                    category="method",
                                    message=(
                                        f"'{attr_name}=\"{url}\"' uses {method} "
                                        f"but route '{route_path}' only allows "
                                        f"{', '.join(sorted(methods))}."
                                    ),
                                    template=template_name,
                                    route=route_path,
                                )
                            )
                        matched = True
                        break
                if not matched:
                    result.issues.append(
                        ContractIssue(
                            severity=Severity.ERROR,
                            category="target",
                            message=f"'{attr_name}=\"{url}\"' has no matching route.",
                            template=template_name,
                        )
                    )

        all_ids: set[str] = set()
        for source in template_sources.values():
            all_ids.update(extract_static_ids(source))
            all_ids.update(extract_fragment_island_ids(source))
            all_ids.update(extract_wizard_form_ids(source))
        hx_target_issues, hx_validated = check_hx_target_selectors(template_sources, all_ids)
        result.hx_targets_validated = hx_validated
        result.issues.extend(hx_target_issues)
        result.issues.extend(check_hx_indicator_selectors(template_sources, all_ids))
        result.issues.extend(check_selector_syntax(template_sources))
        result.issues.extend(check_hx_boost(template_sources))
        result.issues.extend(check_swap_safety(template_sources))
        result.issues.extend(check_sse_self_swap(template_sources))
        broad_targets = collect_broad_targets(template_sources)
        result.issues.extend(check_sse_connect_scope(template_sources, broad_targets))
        result.issues.extend(check_sse_event_crossref(template_sources, router))
        result.issues.extend(check_layout_chains(snapshot.layout_chains, template_sources))
        result.issues.extend(
            check_island_mounts(template_sources, strict=snapshot.islands_contract_strict)
        )
        for template_name, source in template_sources.items():
            if template_name.startswith(("chirp/", "chirpui/")):
                continue
            result.issues.extend(check_accessibility(source, template_name))

        result.issues.extend(validate_form_contracts(result, router, template_sources))

        page_route_paths = snapshot.page_route_paths
        referenced_route_paths: set[str] = {
            route.path for route in router.routes if getattr(route, "referenced", False)
        }
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
        referenced_templates: set[str] = set()
        for route in router.routes:
            template = getattr(route, "template", None)
            if template is not None:
                referenced_templates.add(template)
            route_contract = getattr(route.handler, "_chirp_contract", None)
            if route_contract is None:
                continue
            if isinstance(route_contract.returns, FragmentContract):
                referenced_templates.add(route_contract.returns.template)
            elif isinstance(route_contract.returns, SSEContract):
                for fragment_contract in route_contract.returns.fragments:
                    referenced_templates.add(fragment_contract.template)
        for source in template_sources.values():
            referenced_templates.update(extract_template_references(source))
        referenced_templates.update(snapshot.page_templates)

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
