"""TemplateStream client-shape contract checks.

``TemplateStream`` always renders a whole template file (chunked HTTP). It is
not a fragment return type — pairing it with htmx ``hx-target`` swaps nests a
full document inside a div. See ``docs/hypermedia-footguns.md``.
"""

import ast
import inspect
import re
import textwrap
from typing import Any

from chirp.routing.router import Router

from .patterns import METHOD_POST
from .routes import build_route_index, collect_route_paths, find_matching_route
from .rules_sse import _call_name, strip_template_comments
from .types import ContractIssue, Severity

_FULL_PAGE_MARKERS = re.compile(
    r"<!doctype|<html\b|\{%-?\s*extends\s",
    re.IGNORECASE,
)

_MUTATING_TAG = re.compile(
    r"<(?P<tag>form|button|a|div|span|input)\b(?P<attrs>[^>]*)\s*/?>",
    re.IGNORECASE,
)
_HX_MUTATION = re.compile(r"\bhx-(?:post|put|patch|delete)\s*=\s*[\"']([^\"']+)[\"']", re.IGNORECASE)
_ACTION_URL = re.compile(r"\baction\s*=\s*[\"']([^\"']+)[\"']", re.IGNORECASE)
_HX_TARGET = re.compile(r"\bhx-target\s*=\s*[\"']#([^\"']+)[\"']", re.IGNORECASE)


def _template_stream_template(handler: Any) -> str | None:
    """Return the template path from a literal ``TemplateStream(...)`` return."""
    try:
        source = inspect.getsource(inspect.unwrap(handler))
        tree = ast.parse(textwrap.dedent(source))
    except OSError, SyntaxError, TypeError:
        return None

    for node in ast.walk(tree):
        if not isinstance(node, ast.Return) or not isinstance(node.value, ast.Call):
            continue
        if _call_name(node.value.func) != "TemplateStream":
            continue
        if node.value.args and isinstance(node.value.args[0], ast.Constant) and isinstance(
            node.value.args[0].value, str
        ):
            return node.value.args[0].value
        for kw in node.value.keywords:
            if (
                kw.arg in ("template", "template_name")
                and isinstance(kw.value, ast.Constant)
                and isinstance(kw.value.value, str)
            ):
                return kw.value.value
    return None


def _collect_template_stream_routes(router: Router) -> dict[str, str]:
    """Map route path → template name for handlers returning ``TemplateStream``."""
    routes: dict[str, str] = {}
    for route in router.routes:
        template_name = _template_stream_template(route.handler)
        if template_name:
            routes[route.path] = template_name
    return routes


def _iter_htmx_targeted_mutations(source: str) -> list[tuple[str, str]]:
    """Yield ``(url, target_id)`` for mutating elements with an explicit ``hx-target``."""
    stripped = strip_template_comments(source)
    hits: list[tuple[str, str]] = []
    for match in _MUTATING_TAG.finditer(stripped):
        attrs = match.group("attrs")
        target_match = _HX_TARGET.search(attrs)
        if not target_match:
            continue
        target_id = target_match.group(1)

        url: str | None = None
        hx_match = _HX_MUTATION.search(attrs)
        if hx_match:
            url = hx_match.group(1).strip()
        else:
            action_match = _ACTION_URL.search(attrs)
            if action_match and METHOD_POST.search(attrs):
                url = action_match.group(1).strip()

        if not url or url.startswith(("#", "javascript:")) or "{{" in url or "{%" in url:
            continue
        if not url.startswith("/"):
            continue
        hits.append((url, target_id))
    return hits


def check_template_stream_client_shape(
    template_sources: dict[str, str],
    router: Router,
) -> list[ContractIssue]:
    """Warn when htmx swaps a ``TemplateStream`` response into a fragment target."""
    template_stream_routes = _collect_template_stream_routes(router)
    if not template_stream_routes:
        return []

    route_paths = collect_route_paths(router)
    static_routes, parametric_routes = build_route_index(route_paths)
    issues: list[ContractIssue] = []

    for template_name, source in template_sources.items():
        if template_name.startswith(("chirp/", "chirpui/")):
            continue
        for url, target_id in _iter_htmx_targeted_mutations(source):
            route_match = find_matching_route(url, static_routes, parametric_routes)
            if route_match is None:
                continue
            matched_route, _methods = route_match
            streamed_template = template_stream_routes.get(matched_route)
            if streamed_template is None:
                continue

            full_page = bool(
                _FULL_PAGE_MARKERS.search(template_sources.get(streamed_template, ""))
            )
            page_hint = (
                " The streamed template looks like a full HTML document"
                if full_page
                else ""
            )
            issues.append(
                ContractIssue(
                    severity=Severity.WARNING,
                    category="template_stream_client_shape",
                    message=(
                        f'htmx swaps route "{matched_route}" (TemplateStream → '
                        f'"{streamed_template}") into "#{target_id}". '
                        "TemplateStream renders the whole template file — use a plain "
                        "form POST for full-page navigation, or return Fragment/EventStream "
                        "for in-place swaps."
                        f"{page_hint}."
                    ),
                    template=template_name,
                    route=matched_route,
                    details=f"Swap target: #{target_id}; streamed template: {streamed_template}",
                )
            )

    return issues
