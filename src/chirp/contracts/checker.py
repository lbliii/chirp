"""Hypermedia contracts checker orchestration."""

import inspect
import logging
import re
from typing import TYPE_CHECKING

from kida import Environment

from chirp.routing.router import _route_path_has_flask_syntax

from .declarations import FormContract, FragmentContract, SSEContract
from .routes import (
    attr_to_method,
    build_route_index,
    collect_route_paths,
    find_matching_route,
)
from .rules_accessibility import (
    check_accessibility,
    check_heading_order,
    check_image_alt,
    check_label_association,
    check_landmarks,
)
from .rules_alpine_cdn import check_alpine_cdn_urls
from .rules_boundary import check_boundary_coverage
from .rules_chirpui_runtime import check_chirpui_runtime_registration
from .rules_commands import check_command_values, check_commandfor_targets
from .rules_composition import check_page_extends_layout
from .rules_context_cascade import check_context_cascade
from .rules_csrf_forms import check_csrf_form_tokens
from .rules_data_shapes import check_data_shapes
from .rules_debug_wiring import check_debug_wiring
from .rules_defer_falsy import check_defer_falsy_conditionals
from .rules_form_routes import check_form_action_contracts
from .rules_forms import validate_form_contracts
from .rules_fragment_scope import check_fragment_block_scope
from .rules_fragment_targets import check_fragment_target_orphans
from .rules_htmx import (
    check_hx_boost,
    check_hx_indicator_selectors,
    check_hx_target_selectors,
    check_selector_syntax,
)
from .rules_htmx_provisioned import check_htmx_provisioned
from .rules_inline import check_inline_templates
from .rules_islands import check_island_mounts
from .rules_kida_analysis import (
    check_component_calls,
    check_template_context_contracts,
    check_template_escape_audit,
    check_template_privacy,
    collect_literal_attributes,
    literal_href_references,
    literal_htmx_partial_sources,
    literal_hx_target_selectors,
    literal_route_targets,
    literal_static_ids,
)
from .rules_layout import check_layout_chains
from .rules_live_blocks import check_live_blocks
from .rules_macro_css import check_macro_css
from .rules_mount_app import check_mount_app_merge
from .rules_oob_registry import check_oob_registry_coverage
from .rules_oob_targets import check_oob_targets
from .rules_page_handlers import check_page_handlers
from .rules_page_shell import check_page_shell_contracts
from .rules_reactive import (
    check_reactive_audience_scopes,
    check_reactive_block_existence,
    check_reactive_derivation_dag,
    check_reactive_emitted_paths,
)
from .rules_route_contract import (
    check_context_provider_signatures,
    check_duplicate_routes,
    check_route_file_consistency,
    check_section_bindings,
    check_section_coverage,
    check_section_tab_hrefs,
    check_shell_mode_blocks,
)
from .rules_route_names import check_route_names
from .rules_shapecheck import check_shapecheck
from .rules_sse import (
    check_sse_connect_scope,
    check_sse_event_crossref,
    check_sse_self_swap,
)
from .rules_suspense_defer import (
    SUSPENSE_DEFER_BLOCKS,
    check_suspense_undiscoverable,
)
from .rules_swap import check_swap_safety, check_view_transition_safety, collect_broad_targets
from .rules_unreachable_blocks import check_unreachable_blocks
from .rules_vary import check_vary_coverage
from .template_scan import (
    extract_fragment_island_ids,
    extract_href_references,
    extract_htmx_partial_sources,
    extract_ids_with_disinherit,
    extract_legacy_action_contracts,
    extract_static_ids,
    extract_targets_from_source,
    extract_template_references,
    extract_wizard_form_ids,
    load_template_sources,
    resolve_template_reference,
)
from .types import CheckResult, ContractCoverage, ContractIssue, Severity

# Page/Suspense: filesystem and imperative routes return these with a template path.
_TEMPLATE_CALL_PATTERN = re.compile(
    r'(?:Template|Fragment|Page|Suspense|Stream|TemplateStream)\s*\(\s*["\']([^"\']+\.html)["\']'
)

if TYPE_CHECKING:
    from chirp.app import App
    from chirp.app.state import ContractCheckSnapshot
    from chirp.data.schema.types import SchemaSnapshot


def _build_coverage(snapshot: ContractCheckSnapshot) -> ContractCoverage:
    routes = tuple(getattr(snapshot.router, "routes", ()))
    post_routes = 0
    post_routes_with_form_contract = 0
    mounted_page_routes = 0
    mounted_page_routes_with_contract = 0
    for route in routes:
        contract = getattr(route.handler, "_chirp_contract", None)
        if "POST" in getattr(route, "methods", frozenset()):
            post_routes += 1
            if contract is not None and isinstance(getattr(contract, "form", None), FormContract):
                post_routes_with_form_contract += 1
        if getattr(route, "page_source_handler", None) is not None:
            mounted_page_routes += 1
            if contract is not None:
                mounted_page_routes_with_contract += 1
    fragment_registry = snapshot.fragment_target_registry
    oob_registry = snapshot.oob_registry
    return ContractCoverage(
        post_routes=post_routes,
        post_routes_with_form_contract=post_routes_with_form_contract,
        mounted_page_routes=mounted_page_routes,
        mounted_page_routes_with_contract=mounted_page_routes_with_contract,
        page_shell_contracts=len(fragment_registry.registered_contracts),
        page_shell_required_blocks=len(fragment_registry.required_fragment_blocks),
        fragment_targets_registered=len(fragment_registry.registered_targets),
        oob_regions_registered=len(oob_registry.registered_blocks) if oob_registry else 0,
    )


def _build_contract_schema(migrations_dir: str | None) -> SchemaSnapshot | None:
    """Build the declared schema snapshot from a migrations directory, or None.

    Mirrors ``chirp.app._build_contract_schema`` for the fallback snapshot
    builder. Returns ``None`` for db-less apps so the ``data`` shape contract is
    a silent no-op, and swallows malformed-migration errors (data is optional).
    """
    if not migrations_dir:
        return None
    try:
        from chirp.data.schema.parse import schema_from_migrations

        return schema_from_migrations(migrations_dir)
    except Exception:
        return None


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
        handler = route.handler
        page_src = getattr(route, "page_source_handler", None)
        handler_for_source = page_src if page_src is not None else handler
        try:
            src = inspect.getsource(handler_for_source)
            for m in _TEMPLATE_CALL_PATTERN.finditer(src):
                referenced_templates.add(m.group(1))
        except TypeError, OSError:
            pass
        contract = getattr(handler, "_chirp_contract", None)
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


def _collect_defer_blocks_templates(router: object) -> frozenset[str]:
    """Templates whose route handler passes ``defer_blocks=`` to Suspense.

    Those handlers bypass auto-discovery, so the templates they render are
    exempt from the ``suspense_defer`` check. Conservative by design: any
    handler source containing a ``defer_blocks=`` kwarg exempts every template
    that handler references via a ``Suspense(...)``-style call.
    """
    exempt: set[str] = set()
    for route in getattr(router, "routes", []):
        handler = getattr(route, "handler", None)
        page_src = getattr(route, "page_source_handler", None)
        handler_for_source = page_src if page_src is not None else handler
        if handler_for_source is None:
            continue
        try:
            src = inspect.getsource(handler_for_source)
        except TypeError, OSError:
            continue
        if not SUSPENSE_DEFER_BLOCKS.search(src):
            continue
        for match in _TEMPLATE_CALL_PATTERN.finditer(src):
            exempt.add(match.group(1))
    return frozenset(exempt)


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

    kida_env = app._kida_env
    ts: dict[str, str] = {}
    if kida_env is not None and kida_env.loader is not None:
        ts = load_template_sources(kida_env)

    migrations_dir = getattr(app._mutable_state, "migrations_dir", None)
    schema = _build_contract_schema(migrations_dir)

    return _Snapshot(
        router=router,
        kida_env=kida_env,
        layout_chains=getattr(app, "_discovered_layout_chains", []),
        page_route_paths=getattr(app, "_page_route_paths", set()),
        page_leaf_templates=getattr(app, "_page_leaf_templates", set()),
        page_templates=getattr(app, "_page_templates", set()),
        fragment_target_registry=app._mutable_state.fragment_target_registry,
        islands_contract_strict=app.config.islands_contract_strict,
        oob_registry=getattr(app._runtime_state, "oob_registry", None),
        sections=getattr(app._mutable_state, "sections", {}),
        route_metas=getattr(app._mutable_state, "route_metas", {}),
        route_templates=getattr(app._mutable_state, "route_templates", {}),
        discovered_routes=getattr(app._mutable_state, "discovered_routes", []),
        page_handler_findings=list(getattr(app._mutable_state, "page_handler_findings", [])),
        route_name_collisions=dict(getattr(app._runtime_state, "route_name_collisions", {})),
        mount_app_skips=list(getattr(app._mutable_state, "mount_app_skips", [])),
        template_sources=ts,
        extras=dict(getattr(app._mutable_state, "contract_check_data", {})),
        schema=schema,
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
    result.coverage = _build_coverage(snapshot)
    middleware_list = getattr(getattr(app, "_mutable_state", None), "middleware_list", [])

    route_paths = collect_route_paths(router)
    result.routes_checked = len(route_paths)

    # Page-handler findings don't require a kida env — emit them unconditionally
    # so action-only / API-only apps still get the startup signal.
    result.issues.extend(check_page_handlers(snapshot.page_handler_findings))
    result.issues.extend(check_route_names(snapshot.route_name_collisions))
    result.issues.extend(check_mount_app_merge(snapshot.mount_app_skips))
    result.issues.extend(check_debug_wiring(snapshot.debug_wiring))

    referenced_templates_from_routes, referenced_route_paths = _route_prepass(
        router, kida_env, result
    )
    check_inline_templates(router, result)

    template_sources = snapshot.template_sources
    if kida_env is not None and kida_env.loader is not None:
        if not template_sources:
            template_sources = load_template_sources(kida_env)
        result.templates_scanned = len(template_sources)
        result.issues.extend(check_chirpui_runtime_registration(template_sources, snapshot.extras))
        template_aliases = getattr(kida_env, "template_aliases", None)
        referenced_paths: set[str] = set()
        static_routes, parametric_routes = build_route_index(route_paths)
        literal_attrs_by_template = collect_literal_attributes(kida_env, template_sources)

        all_ids: set[str] = set()
        static_ids: set[str] = set()
        ids_with_disinherit: set[str] = set()
        referenced_templates_from_sources: set[str] = set()

        for template_name, source in template_sources.items():
            if template_name.startswith("chirpui/"):
                continue
            literal_attrs = literal_attrs_by_template.get(template_name, ())
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
            for target in literal_route_targets(literal_attrs):
                if target not in targets:
                    targets.append(target)
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
            s = extract_static_ids(source) | literal_static_ids(literal_attrs)
            static_ids.update(s)
            all_ids.update(s)
            all_ids.update(extract_fragment_island_ids(source))
            all_ids.update(extract_wizard_form_ids(source))
            ids_with_disinherit.update(extract_ids_with_disinherit(source))
            referenced_templates_from_sources.update(
                resolve_template_reference(ref, template_name, template_aliases)
                for ref in extract_template_references(source)
            )
            for href_url in extract_href_references(source) | literal_href_references(
                literal_attrs
            ):
                href_match = find_matching_route(href_url, static_routes, parametric_routes)
                if href_match is not None:
                    referenced_paths.add(href_match[0])
            partial_urls = list(extract_htmx_partial_sources(source))
            for partial_url in literal_htmx_partial_sources(literal_attrs):
                if partial_url not in partial_urls:
                    partial_urls.append(partial_url)
            for partial_url in partial_urls:
                partial_match = find_matching_route(partial_url, static_routes, parametric_routes)
                if partial_match is not None:
                    referenced_paths.add(partial_match[0])
                else:
                    result.issues.append(
                        ContractIssue(
                            severity=Severity.ERROR,
                            category="htmx_partial",
                            message=(f'<htmx-partial src="{partial_url}"> has no matching route.'),
                            template=template_name,
                        )
                    )

        literal_hx_targets = {
            template_name: literal_hx_target_selectors(attrs)
            for template_name, attrs in literal_attrs_by_template.items()
        }
        hx_target_issues, hx_validated = check_hx_target_selectors(
            template_sources,
            all_ids,
            literal_selectors=literal_hx_targets,
        )
        result.hx_targets_validated = hx_validated
        result.issues.extend(hx_target_issues)
        result.issues.extend(check_hx_indicator_selectors(template_sources, all_ids))
        result.issues.extend(check_selector_syntax(template_sources))
        result.issues.extend(check_csrf_form_tokens(template_sources, middleware_list))
        from .rules_i18n import check_translation_keys

        result.issues.extend(check_translation_keys(template_sources, app.config))
        result.issues.extend(check_hx_boost(template_sources))
        commandfor_issues, commandfor_validated = check_commandfor_targets(
            template_sources, all_ids
        )
        result.commandfor_validated = commandfor_validated
        result.issues.extend(commandfor_issues)
        result.issues.extend(check_command_values(template_sources))
        result.issues.extend(
            check_swap_safety(
                template_sources,
                all_ids=static_ids,
                all_ids_with_disinherit=ids_with_disinherit,
                template_aliases=template_aliases,
            )
        )
        result.issues.extend(check_view_transition_safety(template_sources))
        result.issues.extend(check_sse_self_swap(template_sources))
        broad_targets = collect_broad_targets(template_sources)
        result.issues.extend(check_sse_connect_scope(template_sources, broad_targets))
        result.issues.extend(check_sse_event_crossref(template_sources, router))
        result.issues.extend(
            check_layout_chains(
                snapshot.layout_chains,
                template_sources,
                fragment_target_registry=snapshot.fragment_target_registry,
            )
        )
        # Landmark check: root layout templates define the page shell (<html>/<body>)
        # and contain {% block %} for child templates to fill.  Leaf pages also
        # contain {% block %} but inherit landmarks from their layout, so we
        # only check templates that define the document structure.
        layout_sources = {
            name: src
            for name, src in template_sources.items()
            if ("{% block " in src or "{%block " in src)
            and ("<html" in src.lower() or "<body" in src.lower() or "<!doctype" in src.lower())
            and not name.startswith(("chirp/", "chirpui/"))
        }
        result.issues.extend(check_landmarks(layout_sources))
        result.issues.extend(
            check_page_shell_contracts(
                snapshot.page_leaf_templates,
                snapshot.fragment_target_registry,
                kida_env,
            )
        )
        result.issues.extend(
            check_fragment_target_orphans(
                snapshot.fragment_target_registry,
                snapshot.page_leaf_templates,
                kida_env,
            )
        )
        result.issues.extend(
            check_unreachable_blocks(
                snapshot.page_leaf_templates,
                kida_env,
                extras=snapshot.extras,
            )
        )
        result.issues.extend(
            check_page_extends_layout(
                snapshot.page_leaf_templates,
                snapshot.layout_chains,
                kida_env,
            )
        )
        result.issues.extend(check_section_bindings(snapshot.route_metas, snapshot.sections))
        discovered = getattr(snapshot, "discovered_routes", [])
        meta_provider_paths = {
            r.url_path for r in discovered if getattr(r, "meta_provider", None) is not None
        }
        result.issues.extend(
            check_section_coverage(
                snapshot.route_metas,
                snapshot.sections,
                snapshot.page_route_paths,
                meta_provider_paths,
            )
        )
        result.issues.extend(
            check_shell_mode_blocks(
                snapshot.route_metas,
                snapshot.route_templates,
                snapshot.fragment_target_registry,
                kida_env,
            )
        )
        action_route_paths = {
            r.url_path for r in discovered if getattr(r, "kind", None) == "action"
        }
        result.issues.extend(
            check_route_file_consistency(
                snapshot.route_metas,
                snapshot.page_route_paths,
                action_route_paths,
                meta_provider_paths,
            )
        )
        result.issues.extend(check_duplicate_routes(discovered))
        result.issues.extend(check_section_tab_hrefs(snapshot.sections, snapshot.page_route_paths))
        providers = getattr(app._mutable_state, "providers", None)
        result.issues.extend(
            check_context_provider_signatures(
                discovered,
                providers,
            )
        )
        result.issues.extend(
            check_context_cascade(
                discovered,
                providers,
            )
        )
        result.issues.extend(
            check_island_mounts(template_sources, strict=snapshot.islands_contract_strict)
        )
        result.issues.extend(check_vary_coverage(template_sources))
        for template_name, source in template_sources.items():
            if template_name.startswith(("chirp/", "chirpui/")):
                continue
            result.issues.extend(check_accessibility(source, template_name))
            result.issues.extend(check_label_association(source, template_name))
            result.issues.extend(check_image_alt(source, template_name))
            result.issues.extend(check_heading_order(source, template_name))

        result.issues.extend(validate_form_contracts(result, router, template_sources))
        result.issues.extend(check_oob_targets(template_sources, all_ids))
        # OOB registry coverage: warn when registered blocks are missing from layouts
        layout_template_names: list[str] = []
        for chain in snapshot.layout_chains:
            for layout_info in getattr(chain, "layouts", ()):
                name = getattr(layout_info, "template_name", None)
                if name and name not in layout_template_names:
                    layout_template_names.append(name)
        result.issues.extend(
            check_oob_registry_coverage(
                snapshot.oob_registry,
                layout_template_names,
                kida_env,
            )
        )
        result.issues.extend(check_form_action_contracts(template_sources, router))
        result.issues.extend(check_boundary_coverage(template_sources))
        result.issues.extend(check_alpine_cdn_urls(template_sources))
        # #148 child 1: core macro classes (chirp-dropdown/field--error/...) have
        # no backing CSS without chirp-ui. extras['chirpui_components'] is a non-None
        # mapping/frozenset when use_chirp_ui(app) ran; falsy/None means inactive.
        result.issues.extend(
            check_macro_css(
                template_sources,
                chirpui_active=bool(snapshot.extras.get("chirpui_components")),
            )
        )
        # #185: hx-*/sse-* attributes are inert unless htmx is provisioned via
        # AppConfig(htmx=True) or an htmx <script> marker in the template chain.
        result.issues.extend(
            check_htmx_provisioned(
                template_sources,
                htmx_config_enabled=bool(app.config.htmx),
            )
        )
        result.issues.extend(check_defer_falsy_conditionals(template_sources))
        result.issues.extend(
            check_suspense_undiscoverable(
                template_sources,
                kida_env,
                defer_blocks_templates=_collect_defer_blocks_templates(router),
            )
        )
        result.issues.extend(check_fragment_block_scope(template_sources, kida_env))
        result.issues.extend(
            check_template_context_contracts(kida_env, template_sources, snapshot.extras)
        )
        component_issues, component_count = check_component_calls(kida_env, template_sources)
        result.component_calls_validated += component_count
        result.issues.extend(component_issues)
        result.issues.extend(check_template_escape_audit(kida_env, template_sources))
        result.issues.extend(check_template_privacy(kida_env, template_sources))

        # Reactive bus contract checks (if a DependencyIndex is registered)
        reactive_index = getattr(app, "_reactive_index", None) or snapshot.extras.get(
            "reactive_index"
        )
        if reactive_index is not None:
            result.issues.extend(check_reactive_block_existence(reactive_index, kida_env))
            result.issues.extend(check_reactive_derivation_dag(reactive_index))
            result.issues.extend(
                check_reactive_emitted_paths(
                    reactive_index,
                    snapshot.extras.get("reactive_emitted_paths"),
                )
            )
        result.issues.extend(
            check_reactive_audience_scopes(
                snapshot.extras.get("reactive_audience_scopes"),
                snapshot.extras.get("reactive_connection_scopes"),
            )
        )

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
                    severity=Severity.WARNING,
                    category="dead",
                    message=(
                        f"Template '{template_name}' is not referenced by any route or template. "
                        f"Remove it or add a route that uses it."
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
                logging.getLogger("chirp.contracts").debug(
                    "Fragment context check failed for route %s",
                    route.path,
                    exc_info=True,
                )

    # Safety checks: catch silent failure modes
    from chirp.contracts.rules_safety import (
        check_allowed_hosts,
        check_csrf_session_order,
        check_middleware_signatures,
        check_secret_key,
        check_sse_speculation,
    )

    result.issues.extend(check_sse_speculation(router))
    result.issues.extend(check_csrf_session_order(middleware_list))
    result.issues.extend(check_middleware_signatures(middleware_list))
    result.issues.extend(check_secret_key(app.config))
    result.issues.extend(check_allowed_hosts(app.config))

    # Deploy-preflight: production misconfiguration (debug/metrics/sentry)
    from chirp.contracts.rules_deploy import (
        check_debug_in_production,
        check_metrics_path_collision,
        check_sentry_sample_rate,
    )

    result.issues.extend(check_debug_in_production(app.config))
    result.issues.extend(check_metrics_path_collision(app.config, router))
    result.issues.extend(check_sentry_sample_rate(app.config))

    # Security stack: mutating routes need CSRF/Session/SecurityHeaders.
    # discovered_routes carries filesystem PageRoutes (which expose `.actions`)
    # so a GET-only page backed by _actions.py form actions is treated as
    # mutating, not just method-mutating router routes.
    from chirp.contracts.rules_security_stack import check_security_stack

    result.issues.extend(
        check_security_stack(
            router,
            app.config,
            middleware_list,
            getattr(snapshot, "discovered_routes", []),
        )
    )

    # CSP-nonce: framework inline scripts are built through per-request snippet
    # factories (#195), so they carry the live nonce when a nonce mechanism is
    # active (CSPNonceMiddleware / csp_nonce_enabled). This rule ERRORs (env-aware)
    # only on the genuinely un-nonceable case: an inline-forbidding CSP in force
    # with no nonce mechanism while an inline-script feature is enabled. See
    # rules_csp_nonce.
    from chirp.contracts.rules_csp_nonce import check_csp_nonce

    result.issues.extend(
        check_csp_nonce(
            router,
            app.config,
            middleware_list,
            getattr(snapshot, "discovered_routes", []),
        )
    )
    # Static streaming: StaticFiles must keep a sane stream threshold so large
    # files stream from disk rather than buffering into memory (#178).
    from chirp.contracts.rules_static_streaming import check_static_streaming

    result.issues.extend(check_static_streaming(middleware_list))

    # No-JS progressive-enhancement floor
    from chirp.contracts.rules_nojs_floor import check_nojs_mutation_fallback

    result.issues.extend(check_nojs_mutation_fallback(router))

    # Typed-SQL column-mapping shape contract (#159): SELECTed columns that
    # map to no field on the fetch(cls, ...) dataclass (and are unknown to the
    # declared schema) are real drift. No-op for db-less apps -- snapshot.schema
    # is None without a migrations dir. See rules_data_shapes.
    result.issues.extend(check_data_shapes(router, snapshot.schema))

    # Verified-Shape render contract (#166/#168/#173): block field reads vs the
    # bound @shape's provided columns/computed, plus surface-contract registry
    # drift. Runs even with no contract data (auto shape_registry). The whole
    # rule is wrapped so an analysis error returns [] and never crashes check().
    result.issues.extend(check_shapecheck(snapshot))

    live_blocks = getattr(app._mutable_state, "live_blocks", {})
    result.issues.extend(check_live_blocks(live_blocks, router, snapshot.route_templates, kida_env))

    # Run registered plugin checks
    registered_checks = getattr(app, "_mutable_state", None)
    if registered_checks is not None:
        for check_fn in getattr(registered_checks, "contract_checks", ()):
            try:
                check_fn(snapshot, result)
            except Exception as exc:
                name = getattr(check_fn, "__name__", None) or type(check_fn).__name__
                result.issues.append(
                    ContractIssue(
                        severity=Severity.ERROR,
                        category="plugin_check_error",
                        message=f"Custom check '{name}' raised: {exc}",
                    )
                )

    # Apply severity overrides as post-processing
    overrides: dict[str, Severity] = {}
    if registered_checks is not None:
        overrides = getattr(registered_checks, "contract_severity_overrides", {})
    if overrides:
        result.issues = [
            ContractIssue(
                severity=overrides[issue.category],
                category=issue.category,
                message=issue.message,
                template=issue.template,
                route=issue.route,
                details=issue.details,
            )
            if issue.category in overrides
            else issue
            for issue in result.issues
        ]

    return result
