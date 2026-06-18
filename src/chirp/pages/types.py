"""Data models for filesystem-based page routing.

Immutable frozen dataclasses representing discovered layouts, context
providers, and page routes.  Built once at app startup during discovery.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal

type RouteKind = Literal["page", "detail", "action", "redirect", "composition"]

type OutletSwapMode = Literal["compose", "replace"]


@dataclass(frozen=True, slots=True)
class LayoutPreset:
    """Named defaults for filesystem layout metadata.

    Presets let apps and extensions encode a conventional shell shape once and
    keep `_layout.html` focused on route-tree intent. Explicit comments in the
    layout always override preset defaults.
    """

    name: str
    target: str | None = None
    domain_name: str | None = None
    shell_name: str | None = None
    swap_scope_name: str | None = None
    outlet_target_id: str | None = None
    frame_targets: frozenset[str] | None = None
    outlet_mode: OutletSwapMode | None = None


type AuthMode = Literal["all", "any"]


@dataclass(frozen=True, slots=True)
class AuthSpec:
    """Structured declarative auth requirement for ``RouteMeta.auth``.

    This is the data-model parity layer for the imperative
    ``@login_required`` / ``@requires`` decorators: a declarative page can now
    express authn-only gating, a permission set with ``all``/``any`` matching,
    and a named policy — without embedding a live callable in frozen route
    metadata.

    ``RouteMeta`` is **static serializable data**: ``policy`` is therefore a
    string NAME resolved later against an app policy registry, never a
    ``Callable``. Plain ``str`` ``auth`` values remain fully supported and are
    normalized to an equivalent ``AuthSpec`` (see
    :func:`chirp.security.auth_core.normalize_auth_spec`).

    An ``AuthSpec`` **always requires an authenticated user** — the gate always
    checks ``is_authenticated``. The only way to express an open/optional route
    is ``RouteMeta.auth = None`` (or an open string token ``"none"`` /
    ``"optional"`` / ``""``), NOT an ``AuthSpec``. There is therefore no
    ``required`` flag: an authn-only gate is ``AuthSpec()`` (no permissions, no
    policy).

    Attributes:
        permissions: Required permission names. Empty means authn-only.
        mode: ``"all"`` requires every permission (subset check); ``"any"``
            requires a non-empty intersection.
        policy: Optional policy NAME resolved against the app policy registry
            at request time. Never a callable — keeps ``RouteMeta``
            serializable.
    """

    permissions: tuple[str, ...] = ()
    mode: AuthMode = "all"
    policy: str | None = None


@dataclass(frozen=True, slots=True)
class RouteMeta:
    """Route metadata from ``_meta.py``.

    All fields optional. Static META or meta() callable provides values.

    ``auth`` accepts a plain ``str`` (back-compatible: ``"none"``/``"optional"``
    are open, ``"required"`` is authn-only, any other non-empty string is a
    single required permission) or a structured :class:`AuthSpec` for permission
    sets, ``all``/``any`` matching, and named policies.
    """

    title: str | None = None
    section: str | None = None
    breadcrumb_label: str | None = None
    shell_mode: str | None = None
    auth: str | AuthSpec | None = None
    cache: str | None = None
    tags: tuple[str, ...] = ()


type MetaProvider = Callable[
    ..., RouteMeta | dict[str, Any] | Awaitable[RouteMeta | dict[str, Any]]
]

type TabMatchMode = Literal["exact", "prefix"]


@dataclass(frozen=True, slots=True)
class TabItem:
    """A tab item for section navigation (Chirp ``Section`` + chirp-ui route tabs).

    Optional fields match the dict shape consumed by ``render_route_tabs`` /
    ``tab_is_active`` in chirp-ui: ``match`` controls active state for nested URLs.
    See ``SHELL-TABS-CONTRACT.md`` in chirp-ui for the full shell to route-tabs
    data flow.
    """

    label: str
    href: str
    icon: str | None = None
    badge: str | None = None
    match: TabMatchMode = "exact"


@dataclass(frozen=True, slots=True)
class ActionInfo:
    """A named action from ``_actions.py``."""

    name: str
    func: Callable[..., Any]


@dataclass(frozen=True, slots=True)
class Section:
    """A named section with tab items and breadcrumb prefix.

    Register via ``app.register_section()`` before ``mount_pages()``; tab items
    flow to chirp-ui ``render_route_tabs`` through ``resolve_section_context``.
    """

    id: str
    label: str
    tab_items: tuple[TabItem, ...] = ()
    breadcrumb_prefix: tuple[dict[str, str], ...] = ()
    active_prefixes: tuple[str, ...] = ()

    def is_active(self, path: str) -> bool:
        """Return True if *path* matches any of this section's active prefixes."""
        for prefix in self.active_prefixes:
            norm = prefix.rstrip("/") if prefix != "/" else "/"
            if path == norm or (norm != "/" and path.startswith(norm + "/")):
                return True
        return False


@dataclass(frozen=True, slots=True)
class LayoutInfo:
    """A layout template discovered in the filesystem.

    Each ``_layout.html`` declares a shell with a ``{% block content %}``
    slot and a ``{# target: element_id #}`` comment declaring which DOM
    element it owns.

    Optional comments (see filesystem routing docs) declare navigation and
    swap metadata for boosted navigation helpers:

    - ``{# domain: name #}`` — author-facing navigation domain boundary.
    - ``{# shell: name #}`` — this layout introduces a shell boundary.
    - ``{# swap_scope: name #}`` — symbolic scope (e.g. ``shell``, ``page``).
    - ``{# outlet: element_id #}`` — primary navigation outlet for this level
      (defaults to *target* when omitted).
    - ``{# outlet_mode: compose | replace #}`` — how boosted swaps targeting
      ``{# outlet: #}`` relate to layout composition (default ``compose``).
    - ``{# frames: id1, id2 #}`` — optional frame ids (immutable chrome).

    Attributes:
        template_name: Template name for kida (relative to pages root).
        target: DOM element ID this layout renders into.
            ``"body"`` for the root layout, ``"app-content"`` for nested.
        depth: Nesting depth (0 = root).
        domain_name: Optional navigation domain label introduced by this layout.
            When any layout in the chain declares a domain, navigation helpers
            use domain ancestry instead of inferring intent from shell ancestry.
        shell_name: Optional shell boundary label introduced by this layout.
            Descendant routes inherit the full shell path from ancestor layouts.
            Shells describe persistent UI boundaries; they only imply navigation
            intent when no explicit domain metadata is declared.
        swap_scope_name: Optional symbolic scope for ``resolve_navigation_swap``.
        outlet_target_id: Optional primary outlet id for this layout level.
        frame_targets: Optional ids treated as non-swapped frame for validation.
        outlet_mode: ``compose`` (re-run layout shell for the fragment response) vs
            ``replace`` (skip the matched outer layout while still rendering any
            descendant layouts below it; use for scroll/marketing shells where
            the outlet wraps the primary ``{% block content %}`` region).
    """

    template_name: str
    target: str
    depth: int
    shell_name: str | None = None
    swap_scope_name: str | None = None
    outlet_target_id: str | None = None
    frame_targets: frozenset[str] | None = None
    outlet_mode: OutletSwapMode = "compose"
    domain_name: str | None = None


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

    @property
    def domain_layers(self) -> tuple[tuple[str, int], ...]:
        """Return ``(domain_name, layout_index)`` for explicit domain boundaries."""
        return tuple(
            (layout.domain_name, index)
            for index, layout in enumerate(self.layouts)
            if layout.domain_name is not None
        )

    @property
    def domain_path(self) -> tuple[str, ...]:
        """Return the explicit navigation-domain ancestry for this route."""
        return tuple(name for name, _ in self.domain_layers)

    @property
    def shell_layers(self) -> tuple[tuple[str, int], ...]:
        """Return ``(shell_name, layout_index)`` for each declared shell boundary."""
        return tuple(
            (layout.shell_name, index)
            for index, layout in enumerate(self.layouts)
            if layout.shell_name is not None
        )

    @property
    def shell_path(self) -> tuple[str, ...]:
        """Return the inherited shell ancestry for this route.

        The path is derived from boundary layouts that declare
        ``{# shell: name #}``. Layouts without a shell annotation participate
        in composition but do not introduce a new shell boundary.
        """
        return tuple(name for name, _ in self.shell_layers)

    def layout_index_for_shell_depth(self, shell_depth: int) -> int | None:
        """Return the layout index for the Nth shell boundary, or ``None``."""
        if shell_depth <= 0:
            return None
        shell_layers = self.shell_layers
        if shell_depth > len(shell_layers):
            return None
        return shell_layers[shell_depth - 1][1]

    @property
    def navigation_domain_layers(self) -> tuple[tuple[str, int], ...]:
        """Return the ancestry used for route-aware navigation decisions.

        Explicit ``{# domain: #}`` annotations win. When no layout in the chain
        declares a domain, fall back to legacy shell ancestry for backward
        compatibility.
        """
        domain_layers = self.domain_layers
        if domain_layers:
            return domain_layers
        return self.shell_layers

    @property
    def navigation_domain_path(self) -> tuple[str, ...]:
        """Return the effective navigation-domain path for this route."""
        return tuple(name for name, _ in self.navigation_domain_layers)

    def layout_index_for_navigation_depth(self, navigation_depth: int) -> int | None:
        """Return the layout index for the Nth navigation-domain boundary."""
        if navigation_depth <= 0:
            return None
        navigation_layers = self.navigation_domain_layers
        if navigation_depth > len(navigation_layers):
            return None
        return navigation_layers[navigation_depth - 1][1]

    def start_index_for_htmx_target(
        self,
        htmx_target: str | None,
        *,
        omit_outer_layout_targets: frozenset[str] = frozenset(),
    ) -> int | None:
        """Return the layout start index for a boosted navigation target.

        ``omit_outer_layout_targets`` contains target ids whose registered
        fragment config wants to skip the matched outer layout while still
        rendering any descendant shells.
        """
        idx = self.find_start_index_for_target(htmx_target)
        if idx is None or htmx_target is None:
            return idx
        target_id = htmx_target.lstrip("#")
        if target_id in omit_outer_layout_targets:
            return min(idx + 1, len(self.layouts))
        layout = self.layouts[idx]
        if layout.outlet_target_id == target_id and layout.outlet_mode == "replace":
            return min(idx + 1, len(self.layouts))
        return idx

    def find_start_index_for_target(self, htmx_target: str | None) -> int | None:
        """Find the layout index to start rendering from for a given HX-Target.

        Each layout declares ``{# target: element_id #}`` — the DOM
        element it renders *into*.  When ``HX-Target`` matches a
        layout's target, we render from that layout onward (it
        produces the content that fills the targeted element).

        Returns the index of the matched layout, or ``None`` if the
        target doesn't match any layout (treat as fragment).

        Matches ``{# target: element_id #}`` — the DOM node the layout
        renders into — and ``{# outlet: element_id #}`` — the primary
        boosted-navigation outlet (e.g. ``main`` for app shells with
        ``hx-select="#page-content"``).
        """
        if htmx_target is None:
            return None
        # Strip leading # from htmx target
        target_id = htmx_target.lstrip("#")
        for i, layout in enumerate(self.layouts):
            if layout.target == target_id:
                return i
            if layout.outlet_target_id is not None and layout.outlet_target_id == target_id:
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
    meta: RouteMeta | None = None
    meta_provider: MetaProvider | None = None
    actions: tuple[ActionInfo, ...] = ()
    viewmodel_provider: Callable[..., Any] | None = None
    kind: RouteKind = "page"


type PageHandlerFindingKind = Literal["missing", "typo"]


@dataclass(frozen=True, slots=True)
class PageHandlerFinding:
    """A diagnostic finding from page-handler discovery.

    Emitted when a ``page.py`` file either has no recognized HTTP method
    handler (``kind="missing"``) or defines a function whose name looks
    like a handler attempt but isn't recognized (``kind="typo"``).

    Surfaced to ``app.check()`` as ``page_handlers`` contract issues;
    the severity mapping (ERROR for missing, WARNING for typo) is
    applied there, not here.

    Attributes:
        kind: ``"missing"`` or ``"typo"``.
        file: Filesystem path to the ``page.py`` that produced the finding.
        url_path: URL pattern the ``page.py`` would have served.
        function_name: For ``kind="typo"``, the mis-named function; ``None`` for missing.
    """

    kind: PageHandlerFindingKind
    file: str
    url_path: str
    function_name: str | None = None
