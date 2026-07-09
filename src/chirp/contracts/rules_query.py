"""HTTP QUERY startup contracts (#533)."""

from typing import Any

from chirp.http.query_media import (
    normalize_query_media_types,
    query_content_type_supported,
)
from chirp.routing.route import Route
from chirp.routing.router import Router

from .routes import build_route_index, collect_route_paths, find_matching_route
from .template_scan import extract_query_client_references
from .types import ContractIssue, Severity

_CORS_SAFELISTED_MEDIA_RANGES = frozenset(
    {
        "*/*",
        "application/*",
        "application/x-www-form-urlencoded",
        "multipart/*",
        "multipart/form-data",
        "text/*",
        "text/plain",
    }
)


def _query_route_for_path(router: Router, path: str) -> Route | None:
    return next(
        (
            route
            for route in router.routes
            if route.path == path and "QUERY" in {str(method).upper() for method in route.methods}
        ),
        None,
    )


def _query_routes(router: Router) -> tuple[Route, ...]:
    return tuple(
        route
        for route in router.routes
        if "QUERY" in {str(method).upper() for method in route.methods}
    )


def _can_accept_cors_safelisted_content(route: Route) -> bool:
    media_types = route.query_media_types or ()
    return any(
        media_type.split(";", 1)[0].strip().lower() in _CORS_SAFELISTED_MEDIA_RANGES
        for media_type in media_types
    )


def _check_compiled_query_routes(router: Router) -> list[ContractIssue]:
    """Defend the frozen route snapshot even though registration fails first."""
    issues: list[ContractIssue] = []
    for route in router.routes:
        methods = {str(method).upper() for method in route.methods}
        media_types = getattr(route, "query_media_types", None)
        if "QUERY" not in methods:
            if media_types is not None:
                issues.append(
                    ContractIssue(
                        severity=Severity.ERROR,
                        category="query_route",
                        message=(
                            f"Route '{route.path}' declares query_media_types but its frozen "
                            "methods do not include QUERY. Remove the declaration or register "
                            "methods=['QUERY']."
                        ),
                        route=route.path,
                    )
                )
            continue
        if not media_types:
            issues.append(
                ContractIssue(
                    severity=Severity.ERROR,
                    category="query_route",
                    message=(
                        f"QUERY route '{route.path}' has no frozen query_media_types. "
                        "Declare at least one accepted request media range."
                    ),
                    route=route.path,
                )
            )
            continue
        try:
            normalized = normalize_query_media_types(media_types)
        except (TypeError, ValueError) as exc:
            issues.append(
                ContractIssue(
                    severity=Severity.ERROR,
                    category="query_route",
                    message=(
                        f"QUERY route '{route.path}' has invalid frozen query_media_types: {exc}."
                    ),
                    route=route.path,
                )
            )
            continue
        if normalized != media_types:
            issues.append(
                ContractIssue(
                    severity=Severity.ERROR,
                    category="query_route",
                    message=(
                        f"QUERY route '{route.path}' has non-normalized frozen media ranges "
                        f"{media_types!r}; expected {normalized!r}."
                    ),
                    route=route.path,
                )
            )
    return issues


def _check_query_clients(
    router: Router,
    template_sources: dict[str, str],
) -> list[ContractIssue]:
    issues: list[ContractIssue] = []
    static_routes, parametric_routes = build_route_index(collect_route_paths(router))
    for template_name, source in template_sources.items():
        for reference in extract_query_client_references(source):
            match = find_matching_route(reference.url, static_routes, parametric_routes)
            if match is None:
                issues.append(
                    ContractIssue(
                        severity=Severity.ERROR,
                        category="query_target",
                        message=(
                            f"Template '{template_name}' uses {reference.client} QUERY "
                            f"for '{reference.url}', but no route matches that URL."
                        ),
                        template=template_name,
                    )
                )
                continue
            matched_path, methods = match
            if "QUERY" not in methods:
                issues.append(
                    ContractIssue(
                        severity=Severity.ERROR,
                        category="query_method",
                        message=(
                            f"Template '{template_name}' uses {reference.client} QUERY for "
                            f"'{reference.url}', but route '{matched_path}' only allows "
                            f"{', '.join(sorted(methods))}."
                        ),
                        template=template_name,
                        route=matched_path,
                    )
                )
                continue
            query_route = _query_route_for_path(router, matched_path)
            if query_route is None:
                continue
            supported = getattr(query_route, "query_media_types", None) or ()
            if reference.content_type is None:
                if reference.content_type_known:
                    issues.append(
                        ContractIssue(
                            severity=Severity.ERROR,
                            category="query_media_type",
                            message=(
                                f"Template '{template_name}' uses {reference.client} QUERY "
                                f"for route '{matched_path}' without a literal Content-Type. "
                                f"Declare one of: {', '.join(supported)}."
                            ),
                            template=template_name,
                            route=matched_path,
                        )
                    )
                continue
            try:
                accepted = query_content_type_supported(reference.content_type, supported)
            except TypeError, ValueError:
                accepted = False
            if not accepted:
                issues.append(
                    ContractIssue(
                        severity=Severity.ERROR,
                        category="query_media_type",
                        message=(
                            f"Template '{template_name}' sends Content-Type "
                            f"'{reference.content_type}' with {reference.client} QUERY to "
                            f"route '{matched_path}', which accepts: {', '.join(supported)}."
                        ),
                        template=template_name,
                        route=matched_path,
                    )
                )
    return issues


def _check_query_cors(router: Router, middleware_list: list[Any]) -> list[ContractIssue]:
    """Validate cross-origin method and non-safelisted Content-Type preflight."""
    query_routes = _query_routes(router)
    if not query_routes:
        return []
    issues: list[ContractIssue] = []
    for middleware in middleware_list:
        if type(middleware).__name__ != "CORSMiddleware":
            continue
        config = getattr(middleware, "config", None)
        if not getattr(config, "allow_origins", ()):
            continue
        methods = {str(value).upper() for value in getattr(config, "allow_methods", ())}
        if "QUERY" not in methods:
            paths = ", ".join(repr(route.path) for route in query_routes)
            issues.append(
                ContractIssue(
                    severity=Severity.ERROR,
                    category="query_cors",
                    message=(
                        f"CORSMiddleware allows cross-origin requests to QUERY route(s) {paths} "
                        "but CORSConfig.allow_methods omits 'QUERY', so browser preflight will "
                        "reject those requests. Add 'QUERY' to CORSConfig.allow_methods."
                    ),
                )
            )
            continue
        headers = {str(value).lower() for value in getattr(config, "allow_headers", ())}
        if "*" in headers or "content-type" in headers:
            continue
        for route in query_routes:
            if _can_accept_cors_safelisted_content(route):
                continue
            supported = ", ".join(route.query_media_types or ())
            issues.append(
                ContractIssue(
                    severity=Severity.ERROR,
                    category="query_cors",
                    message=(
                        f"QUERY route '{route.path}' accepts only non-CORS-safelisted media "
                        f"ranges ({supported}), but CORSMiddleware does not allow the "
                        "Content-Type request header. Add 'Content-Type' to "
                        "CORSConfig.allow_headers."
                    ),
                    route=route.path,
                )
            )
    return issues


def check_query_contracts(
    router: Router,
    template_sources: dict[str, str],
    middleware_list: list[Any],
) -> list[ContractIssue]:
    """Validate frozen QUERY metadata, literal clients, and CORS declarations."""
    return [
        *_check_compiled_query_routes(router),
        *_check_query_clients(router, template_sources),
        *_check_query_cors(router, middleware_list),
    ]
