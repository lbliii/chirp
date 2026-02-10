"""Filesystem route discovery for the pages/ directory.

Walks the pages directory tree and discovers:
- ``_layout.html`` files as layout templates
- ``_context.py`` files as context providers
- ``.py`` route files as handler modules

Directory names wrapped in ``{braces}`` become path parameters.
``page.py`` maps to the directory URL; other ``.py`` files append
their stem to the path.

Modeled on Bengal's ContentDiscovery but for routes instead of content.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from typing import Any

from chirp.pages.types import ContextProvider, LayoutChain, LayoutInfo, PageRoute

# HTTP method names recognised as handler functions
_HTTP_METHODS = frozenset({"get", "post", "put", "delete", "patch", "head", "options"})

# Regex to extract {# target: element_id #} from layout templates
_TARGET_RE = re.compile(r"\{#\s*target:\s*(\S+)\s*#\}")

# Regex matching {param} directory names
_PARAM_DIR_RE = re.compile(r"^\{(\w+)\}$")


def discover_pages(pages_dir: str | Path) -> list[PageRoute]:
    """Walk a pages directory and discover all routes.

    Args:
        pages_dir: Path to the ``pages/`` directory.

    Returns:
        List of discovered :class:`PageRoute` objects ready for
        registration with the chirp app.
    """
    root = Path(pages_dir).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Pages directory not found: {root}")

    routes: list[PageRoute] = []
    _walk_directory(
        root,
        root,
        url_parts=[],
        layouts=[],
        context_providers=[],
        depth=0,
        routes=routes,
    )
    return routes


def _walk_directory(
    directory: Path,
    root: Path,
    *,
    url_parts: list[str],
    layouts: list[LayoutInfo],
    context_providers: list[ContextProvider],
    depth: int,
    routes: list[PageRoute],
) -> None:
    """Recursively walk a directory, discovering routes and layouts.

    Args:
        directory: Current directory being walked.
        root: Root pages directory (for computing template paths).
        url_parts: URL path segments accumulated so far.
        layouts: Layout chain accumulated from parent directories.
        context_providers: Context providers from parent directories.
        depth: Current nesting depth.
        routes: Accumulator for discovered routes.
    """
    # Check for _layout.html at this level
    layout_file = directory / "_layout.html"
    current_layouts = list(layouts)
    if layout_file.is_file():
        target = _parse_layout_target(layout_file)
        template_name = str(layout_file.relative_to(root))
        layout = LayoutInfo(
            template_name=template_name,
            target=target,
            depth=depth,
        )
        current_layouts.append(layout)

    # Check for _context.py at this level
    context_file = directory / "_context.py"
    current_providers = list(context_providers)
    if context_file.is_file():
        provider = _load_context_provider(context_file, depth)
        if provider is not None:
            current_providers.append(provider)

    # Build the layout chain and provider tuple for routes at this level
    layout_chain = LayoutChain(tuple(current_layouts))
    provider_tuple = tuple(current_providers)

    # Process .py route files at this level
    for item in sorted(directory.iterdir()):
        if not item.is_file():
            continue
        if item.suffix != ".py":
            continue
        if item.name.startswith("_"):
            continue

        _process_route_file(
            item,
            root,
            url_parts=url_parts,
            layout_chain=layout_chain,
            context_providers=provider_tuple,
            routes=routes,
        )

    # Recurse into subdirectories
    for item in sorted(directory.iterdir()):
        if not item.is_dir():
            continue
        if item.name.startswith("_") or item.name.startswith("."):
            continue

        # Check if directory name is a path parameter {param}
        param_match = _PARAM_DIR_RE.match(item.name)
        if param_match:
            segment = "{" + param_match.group(1) + "}"
        else:
            segment = item.name

        _walk_directory(
            item,
            root,
            url_parts=[*url_parts, segment],
            layouts=current_layouts,
            context_providers=current_providers,
            depth=depth + 1,
            routes=routes,
        )


def _parse_layout_target(layout_file: Path) -> str:
    """Extract the target element ID from a layout template.

    Looks for ``{# target: element_id #}`` in the template.
    Defaults to ``"body"`` if not found.
    """
    content = layout_file.read_text(encoding="utf-8")
    match = _TARGET_RE.search(content)
    if match:
        return match.group(1)
    return "body"


def _load_context_provider(context_file: Path, depth: int) -> ContextProvider | None:
    """Load a context() function from a _context.py file.

    Returns None if the module doesn't export a ``context`` function.
    """
    spec = importlib.util.spec_from_file_location(
        f"_context_{depth}",
        context_file,
    )
    if spec is None or spec.loader is None:
        return None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    func = getattr(module, "context", None)
    if func is None or not callable(func):
        return None

    return ContextProvider(
        module_path=str(context_file),
        func=func,
        depth=depth,
    )


def _process_route_file(
    file: Path,
    root: Path,
    *,
    url_parts: list[str],
    layout_chain: LayoutChain,
    context_providers: tuple[ContextProvider, ...],
    routes: list[PageRoute],
) -> None:
    """Load a route .py file and extract handler functions.

    ``page.py`` maps to the directory URL.  Other files append their
    stem to the URL path.

    Handler functions are named after HTTP methods: ``get``, ``post``, etc.
    """
    # Load the module
    module_name = f"_page_{file.stem}_{id(file)}"
    spec = importlib.util.spec_from_file_location(module_name, file)
    if spec is None or spec.loader is None:
        return
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # Determine URL path
    if file.stem == "page":
        url_path = "/" + "/".join(url_parts) if url_parts else "/"
    else:
        parts = [*url_parts, file.stem]
        url_path = "/" + "/".join(parts)

    # Normalise trailing slash for root
    if url_path != "/":
        url_path = url_path.rstrip("/")

    # Find handler functions
    found_handlers: dict[str, Any] = {}
    for method_name in _HTTP_METHODS:
        func = getattr(module, method_name, None)
        if func is not None and callable(func):
            found_handlers[method_name.upper()] = func

    # If no HTTP-method-named functions, look for a default handler
    handler = getattr(module, "handler", None)
    if handler is not None and callable(handler) and not found_handlers:
        # Default to GET for a bare handler
        found_handlers["GET"] = handler

    # Register each handler
    for method, func in found_handlers.items():
        route = PageRoute(
            url_path=url_path,
            handler=func,
            methods=frozenset({method}),
            layout_chain=layout_chain,
            context_providers=context_providers,
            name=None,
        )
        routes.append(route)
