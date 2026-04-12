"""Form action → route contract matching.

Validates that ``<form action="/path" method="post">`` targets have
routes with ``FormContract`` declarations.  This complements the
existing target check (which validates URL existence) by surfacing
POST routes that may silently ignore form data or lack validation.
"""

from __future__ import annotations

import re

from chirp.routing.router import Router

from .declarations import FormContract
from .patterns import METHOD_POST
from .routes import build_route_index, find_matching_route
from .types import ContractIssue, Severity

_FORM_ACTION_RE = re.compile(
    r'<form\b[^>]*\baction\s*=\s*["\']([^"\']+)["\'][^>]*>',
    re.IGNORECASE | re.DOTALL,
)


def check_form_action_contracts(
    template_sources: dict[str, str],
    router: Router,
) -> list[ContractIssue]:
    """Info when a form POSTs to a route without a FormContract.

    Routes that accept POST without declaring a FormContract may
    silently ignore form data or lack proper validation.  This is
    INFO-level because many routes legitimately handle form data
    without a formal contract.
    """
    issues: list[ContractIssue] = []

    # Build set of routes with FormContract
    form_routes: set[str] = set()
    post_routes: set[str] = set()
    for route in router.routes:
        methods = getattr(route, "methods", set())
        if "POST" in methods:
            post_routes.add(route.path)
        contract = getattr(route.handler, "_chirp_contract", None)
        if contract is not None and isinstance(contract.form, FormContract):
            form_routes.add(route.path)

    if not post_routes:
        return issues

    # Build route index for URL matching
    from .routes import collect_route_paths

    route_paths = collect_route_paths(router)
    static_routes, parametric_routes = build_route_index(route_paths)

    # Scan templates for <form action="..." method="post">
    for template_name, source in template_sources.items():
        if template_name.startswith(("chirp/", "chirpui/")):
            continue
        for match in _FORM_ACTION_RE.finditer(source):
            action_url = match.group(1).strip()
            form_tag = match.group(0)

            # Only check POST forms
            if not METHOD_POST.search(form_tag):
                continue

            # Skip dynamic URLs
            if "{{" in action_url or "{%" in action_url:
                continue
            if not action_url.startswith("/"):
                continue

            route_match = find_matching_route(action_url, static_routes, parametric_routes)
            if route_match is None:
                continue  # Already caught by the target checker

            matched_route, _methods = route_match
            if matched_route in post_routes and matched_route not in form_routes:
                issues.append(
                    ContractIssue(
                        severity=Severity.INFO,
                        category="form_contract",
                        message=(
                            f'<form action="{action_url}" method="post"> targets '
                            f"route '{matched_route}' which accepts POST but has "
                            "no FormContract. Consider adding @contract(form=FormContract(...)) "
                            "for validation and type safety."
                        ),
                        template=template_name,
                        route=matched_route,
                    )
                )

    return issues
