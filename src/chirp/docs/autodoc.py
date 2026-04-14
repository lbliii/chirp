"""Autodoc — generate API reference from frozen app state.

Introspects the frozen ``Router`` and ``ToolRegistry`` to produce
``DocPage`` instances that live alongside hand-written markdown in the
same ``DocsCollection``.  All introspection is read-only.

Usage (internal — called by ``DocsPlugin`` after freeze)::

    from chirp.docs.autodoc import generate_autodoc
    pages = generate_autodoc(app)
"""

from __future__ import annotations

import inspect
import re
from typing import TYPE_CHECKING, Any

from kida.template import Markup

from chirp.docs.models import (
    DocMetadata,
    DocPage,
    DocSource,
    ParamDoc,
    RouteDoc,
    ToolDoc,
)

if TYPE_CHECKING:
    from chirp.app import App
    from chirp.routing.route import Route
    from chirp.tools.registry import McpToolInfo

_PARAM_RE = re.compile(r"\{(\w+)(?::(\w+))?\}")

_AUTODOC_CATEGORY = "API Reference"


def generate_autodoc(app: App) -> tuple[DocPage, ...]:
    """Generate API reference pages from frozen app state.

    Must be called after ``app.freeze()``.  Returns ``DocPage`` instances
    with ``source=DocSource.AUTODOC``.
    """
    pages: list[DocPage] = []

    # Routes
    router = app._runtime_state.router
    if router is not None:
        route_docs = introspect_routes(router.routes)
        for i, rd in enumerate(route_docs):
            pages.append(_route_doc_to_page(rd, order=i))

    # Tools
    tool_registry = app._runtime_state.tool_registry
    if tool_registry is not None and len(tool_registry) > 0:
        tool_infos = tool_registry.list_tools()
        tool_docs = introspect_tools(tool_infos)
        for i, td in enumerate(tool_docs):
            pages.append(_tool_doc_to_page(td, order=i))

    return tuple(pages)


# -- Route introspection ---------------------------------------------------


def introspect_routes(routes: list[Route]) -> tuple[RouteDoc, ...]:
    """Extract ``RouteDoc`` from each registered route."""
    docs: list[RouteDoc] = []
    for route in routes:
        handler = route.page_source_handler or route.handler
        docstring = inspect.getdoc(handler)
        params = _extract_route_params(route.path, handler)

        docs.append(
            RouteDoc(
                path=route.path,
                methods=route.methods,
                handler_name=getattr(handler, "__name__", "unknown"),
                docstring=docstring,
                parameters=params,
                template=route.template,
            )
        )
    return tuple(docs)


def _extract_route_params(path: str, handler: Any) -> tuple[ParamDoc, ...]:
    """Extract path parameters from route path and handler signature."""
    path_params: dict[str, str] = {}
    for m in _PARAM_RE.finditer(path):
        path_params[m.group(1)] = m.group(2) or "str"

    # Merge with handler signature for type info and defaults
    params: list[ParamDoc] = []
    try:
        sig = inspect.signature(handler)
    except ValueError, TypeError:
        # Some handlers may not be introspectable
        for name, type_str in path_params.items():
            params.append(ParamDoc(name=name, type_str=type_str, required=True))
        return tuple(params)

    for name, param in sig.parameters.items():
        if name == "request":
            continue
        annotation = param.annotation
        if annotation is inspect.Parameter.empty:
            type_str = path_params.get(name, "str")
        else:
            type_str = getattr(annotation, "__name__", str(annotation))

        has_default = param.default is not inspect.Parameter.empty
        default_str = repr(param.default) if has_default else None

        params.append(
            ParamDoc(
                name=name,
                type_str=type_str,
                required=not has_default,
                default=default_str,
            )
        )

    return tuple(params)


# -- Tool introspection ----------------------------------------------------


def introspect_tools(tool_infos: list[McpToolInfo]) -> tuple[ToolDoc, ...]:
    """Extract ``ToolDoc`` from MCP tool info list."""
    docs: list[ToolDoc] = []
    for info in tool_infos:
        params = _flatten_schema(info["inputSchema"])
        docs.append(
            ToolDoc(
                name=info["name"],
                description=info["description"],
                input_schema=info["inputSchema"],
                parameters=params,
            )
        )
    return tuple(docs)


def _flatten_schema(schema: dict[str, Any]) -> tuple[ParamDoc, ...]:
    """Flatten JSON Schema properties into ``ParamDoc`` tuples."""
    properties = schema.get("properties", {})
    required_set = set(schema.get("required", []))
    params: list[ParamDoc] = []

    for name, prop in properties.items():
        type_str = prop.get("type", "any")
        if type_str == "array":
            items_type = prop.get("items", {}).get("type", "any")
            type_str = f"list[{items_type}]"

        params.append(
            ParamDoc(
                name=name,
                type_str=type_str,
                required=name in required_set,
            )
        )

    return tuple(params)


# -- DocPage generation ----------------------------------------------------


def _slug_for_route(path: str) -> str:
    """Generate a URL-safe slug from a route path.

    ``/contacts/{id}`` → ``api/routes/contacts-id``
    """
    clean = path.strip("/").replace("/", "-").replace("{", "").replace("}", "")
    clean = re.sub(r"[:\s]+", "-", clean)
    clean = re.sub(r"-+", "-", clean).strip("-")
    return f"api/routes/{clean}" if clean else "api/routes/root"


def _slug_for_tool(name: str) -> str:
    """Generate a URL-safe slug from a tool name.

    ``search_docs`` → ``api/tools/search-docs``
    """
    return f"api/tools/{name.replace('_', '-')}"


def _route_doc_to_markdown(rd: RouteDoc) -> str:
    """Render a RouteDoc as markdown (for agent consumption via raw field)."""
    lines = [f"# {rd.path}", ""]
    lines.append(f"**Methods:** {', '.join(sorted(rd.methods))}")
    lines.append(f"**Handler:** `{rd.handler_name}`")
    if rd.template:
        lines.append(f"**Template:** `{rd.template}`")
    lines.append("")

    if rd.docstring:
        lines.append(rd.docstring)
        lines.append("")

    if rd.parameters:
        lines.append("## Parameters")
        lines.append("")
        lines.append("| Name | Type | Required | Default |")
        lines.append("|------|------|----------|---------|")
        for p in rd.parameters:
            default = p.default or "-"
            req = "Yes" if p.required else "No"
            lines.append(f"| `{p.name}` | `{p.type_str}` | {req} | {default} |")
        lines.append("")

    return "\n".join(lines)


def _tool_doc_to_markdown(td: ToolDoc) -> str:
    """Render a ToolDoc as markdown (for agent consumption via raw field)."""
    lines = [f"# {td.name}", ""]
    lines.append(td.description)
    lines.append("")

    if td.parameters:
        lines.append("## Parameters")
        lines.append("")
        lines.append("| Name | Type | Required |")
        lines.append("|------|------|----------|")
        for p in td.parameters:
            req = "Yes" if p.required else "No"
            lines.append(f"| `{p.name}` | `{p.type_str}` | {req} |")
        lines.append("")

    return "\n".join(lines)


def _markdown_to_html(md: str) -> Markup:
    """Simple markdown-to-HTML for autodoc pages.

    Uses MarkdownRenderer if available, falls back to minimal rendering.
    """
    try:
        from chirp.markdown import MarkdownRenderer

        renderer = MarkdownRenderer()
        return renderer.render(md)
    except Exception:
        # Fallback: wrap in <pre> if markdown rendering fails
        from html import escape

        return Markup(f"<pre>{escape(md)}</pre>")


def _route_doc_to_page(rd: RouteDoc, *, order: int) -> DocPage:
    """Convert a RouteDoc to a DocPage."""
    raw = _route_doc_to_markdown(rd)
    html = _markdown_to_html(raw)
    title = f"{', '.join(sorted(rd.methods))} {rd.path}"

    return DocPage(
        slug=_slug_for_route(rd.path),
        title=title,
        raw=raw,
        html=html,
        toc=(),
        metadata=DocMetadata(
            order=order,
            category=_AUTODOC_CATEGORY,
            description=rd.docstring[:120] if rd.docstring else f"Route: {rd.path}",
        ),
        source=DocSource.AUTODOC,
    )


def _tool_doc_to_page(td: ToolDoc, *, order: int) -> DocPage:
    """Convert a ToolDoc to a DocPage."""
    raw = _tool_doc_to_markdown(td)
    html = _markdown_to_html(raw)

    return DocPage(
        slug=_slug_for_tool(td.name),
        title=f"Tool: {td.name}",
        raw=raw,
        html=html,
        toc=(),
        metadata=DocMetadata(
            order=order,
            category=_AUTODOC_CATEGORY,
            description=td.description[:120] if td.description else f"Tool: {td.name}",
        ),
        source=DocSource.AUTODOC,
    )
