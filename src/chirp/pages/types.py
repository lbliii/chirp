"""Data models for filesystem-based page routing.

Immutable frozen dataclasses representing discovered layouts, context
providers, and page routes.  Built once at app startup during discovery.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class LayoutInfo:
    """A layout template discovered in the filesystem.

    Each ``_layout.html`` declares a shell with a ``{% block content %}``
    slot and a ``{# target: element_id #}`` comment declaring which DOM
    element it owns.

    Attributes:
        template_name: Template name for kida (relative to pages root).
        target: DOM element ID this layout renders into.
            ``"body"`` for the root layout, ``"app-content"`` for nested.
        depth: Nesting depth (0 = root).
    """

    template_name: str
    target: str
    depth: int


@dataclass(frozen=True, slots=True)
class LayoutChain:
    """Ordered sequence of layouts from root (outermost) to deepest.

    The chain determines rendering depth based on ``HX-Target``:

    - Full page: render all layouts nested
    - ``HX-Target: #app-content``: find the layout that owns
      ``app-content``, render from the *next* layout down
    - Fragment: render just the targeted block
    """

    layouts: tuple[LayoutInfo, ...] = ()

    def find_start_index_for_target(self, htmx_target: str | None) -> int | None:
        """Find the layout index to start rendering from for a given HX-Target.

        Each layout declares ``{# target: element_id #}`` — the DOM
        element it renders *into*.  When ``HX-Target`` matches a
        layout's target, we render from that layout onward (it
        produces the content that fills the targeted element).

        Returns the index of the matched layout, or ``None`` if the
        target doesn't match any layout (treat as fragment).
        """
        if htmx_target is None:
            return None
        # Strip leading # from htmx target
        target_id = htmx_target.lstrip("#")
        for i, layout in enumerate(self.layouts):
            if layout.target == target_id:
                return i
        return None


@dataclass(frozen=True, slots=True)
class ContextProvider:
    """A ``_context.py`` file's context function.

    Each provider is an async or sync function that receives path
    parameters and returns a dict of context variables.

    Attributes:
        module_path: Filesystem path to the ``_context.py`` file.
        func: The ``context()`` callable from the module.
        depth: Nesting depth (0 = root).
    """

    module_path: str
    func: Callable[..., dict[str, Any] | Awaitable[dict[str, Any]]]
    depth: int


@dataclass(frozen=True, slots=True)
class PageRoute:
    """A discovered page route with its layout chain and context providers.

    Built during filesystem discovery.  Used by ``mount_pages()`` to
    register routes with the chirp app.

    Attributes:
        url_path: URL pattern (e.g., ``/doc/{doc_id}``).
        handler: The route handler callable.
        methods: HTTP methods (e.g., ``frozenset({"GET"})``).
        layout_chain: The sequence of layouts wrapping this route.
        context_providers: Context functions to run, ordered root-first.
        template_name: Template to render (for page routes with templates).
        name: Optional route name.
    """

    url_path: str
    handler: Callable[..., Any]
    methods: frozenset[str]
    layout_chain: LayoutChain = field(default_factory=LayoutChain)
    context_providers: tuple[ContextProvider, ...] = ()
    template_name: str | None = None
    name: str | None = None
