"""Chirp application facade."""

import threading
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from kida import Environment

from chirp._internal.asgi import Receive, Scope, Send
from chirp.config import AppConfig
from chirp.contracts.types import Severity
from chirp.errors import ConfigurationError
from chirp.pages.types import LayoutChain, LayoutPreset, OutletSwapMode, Section
from chirp.templating.fragment_target_registry import PageShellContract
from chirp.templating.integration import render_fragment, render_template
from chirp.templating.returns import Fragment, InlineTemplate, Template

from .compiler import AppCompiler
from .diagnostics import ContractCheckRunner
from .lifecycle import LifecycleCoordinator
from .registry import AppRegistry
from .server import ServerLauncher
from .state import (
    ContractCheckSnapshot,
    MutableAppState,
    PendingRoute,
    PendingTool,
    RuntimeAppState,
)

if TYPE_CHECKING:
    from pounce.server import LifecycleCollector

    from chirp.data.database import Database


# Backwards-compatible symbol aliases (historically imported from chirp.app).
_PendingRoute = PendingRoute
_PendingTool = PendingTool


class App:
    """The chirp application.

    Mutable during setup (route registration, middleware, filters).
    Frozen at runtime when ``app.run()`` or ``__call__()`` is first invoked.
    """

    __slots__ = (
        "_compiler",
        "_contract_checks",
        # Backwards-compatible field aliases (tests and advanced users).
        "_custom_kida_env",
        "_db",
        "_discovered_layout_chains",
        "_error_handlers",
        "_freeze_lock",
        "_freeze_param_providers",
        "_frozen",
        "_kida_env",
        "_lazy_pages_dir",
        "_lifecycle",
        "_middleware",
        "_middleware_list",
        "_migrations_dir",
        "_mutable_state",
        "_page_leaf_templates",
        "_page_route_paths",
        "_page_templates",
        "_pending_domains",
        "_pending_routes",
        "_pending_tools",
        "_providers",
        "_registry",
        "_reload_dirs_extra",
        "_router",
        "_runtime",
        "_runtime_state",
        "_server",
        "_shutdown_hooks",
        "_startup_hooks",
        "_template_filters",
        "_template_globals",
        "_tool_events",
        "_tool_registry",
        "_worker_shutdown_hooks",
        "_worker_startup_hooks",
        "config",
    )

    def __init__(
        self,
        config: AppConfig | None = None,
        *,
        db: Database | str | None = None,
        migrations: str | None = None,
        kida_env: Environment | None = None,
    ) -> None:
        self.config = config or AppConfig()
        self._mutable_state = MutableAppState()
        self._runtime_state = RuntimeAppState()
        self._freeze_lock = threading.Lock()

        if isinstance(db, str):
            from chirp.data.database import Database as _Database

            self._mutable_state.db = _Database(db)
        else:
            self._mutable_state.db = db
        self._mutable_state.migrations_dir = migrations
        self._mutable_state.custom_kida_env = kida_env

        self._registry = AppRegistry(self._mutable_state, self._check_not_frozen)
        self._contract_checks = ContractCheckRunner(self.config)
        self._compiler = AppCompiler(
            self.config, self._registry, self._mutable_state, self._runtime_state
        )
        self._lifecycle = LifecycleCoordinator(
            self.config, self._mutable_state, self._ensure_frozen
        )
        from .runtime import ASGIRuntime

        self._runtime = ASGIRuntime(
            self.config,
            self._mutable_state,
            self._runtime_state,
            self._lifecycle,
            self._ensure_frozen,
        )
        self._server = ServerLauncher(self.config, self._mutable_state)
        self._sync_aliases()

    def _sync_aliases(self) -> None:
        self._pending_routes = self._mutable_state.pending_routes
        self._pending_tools = self._mutable_state.pending_tools
        self._middleware_list = self._mutable_state.middleware_list
        self._error_handlers = self._mutable_state.error_handlers
        self._template_filters = self._mutable_state.template_filters
        self._template_globals = self._mutable_state.template_globals
        self._startup_hooks = self._mutable_state.startup_hooks
        self._shutdown_hooks = self._mutable_state.shutdown_hooks
        self._worker_startup_hooks = self._mutable_state.worker_startup_hooks
        self._worker_shutdown_hooks = self._mutable_state.worker_shutdown_hooks
        self._discovered_layout_chains = self._mutable_state.discovered_layout_chains
        self._lazy_pages_dir = self._mutable_state.lazy_pages_dir
        self._page_route_paths = self._mutable_state.page_route_paths
        self._page_leaf_templates = self._mutable_state.page_leaf_templates
        self._page_templates = self._mutable_state.page_templates
        self._pending_domains = self._mutable_state.pending_domains
        self._providers = self._mutable_state.providers
        self._reload_dirs_extra = self._mutable_state.reload_dirs_extra
        self._db = self._mutable_state.db
        self._migrations_dir = self._mutable_state.migrations_dir
        self._custom_kida_env = self._mutable_state.custom_kida_env
        self._tool_events = self._mutable_state.tool_events
        self._freeze_param_providers = self._mutable_state.freeze_param_providers

        self._frozen = self._runtime_state.frozen
        self._router = self._runtime_state.router
        self._middleware = self._runtime_state.middleware
        self._kida_env = self._runtime_state.kida_env
        self._tool_registry = self._runtime_state.tool_registry

    def _sync_runtime_aliases(self) -> None:
        self._frozen = self._runtime_state.frozen
        self._router = self._runtime_state.router
        self._middleware = self._runtime_state.middleware
        self._kida_env = self._runtime_state.kida_env
        self._tool_registry = self._runtime_state.tool_registry
        self._lazy_pages_dir = self._mutable_state.lazy_pages_dir
        self._runtime_state.contracts_ready = self._runtime_state.frozen and (
            self._runtime_state.router is not None
        )

    def bind_config(self, config: AppConfig) -> None:
        """Set ``config`` on the app and mirror it into internal subsystems.

        The compiler, ASGI runtime, server launcher, lifecycle coordinator, and
        contract checker each hold their own reference from construction.
        Reassigning ``app.config`` alone leaves those stale — use this after
        ``App()`` when CLI helpers or extensions replace fields (e.g. ``debug``,
        ``alpine``, ``dev_browser_reload``) before ``run()``/freeze.
        """
        self.config = config
        self._compiler._config = config
        self._runtime._config = config
        self._server._config = config
        self._lifecycle._config = config
        self._contract_checks._config = config

    def route(
        self,
        path: str,
        *,
        methods: list[str] | None = None,
        name: str | None = None,
        referenced: bool = False,
        template: str | None = None,
        inline: bool = False,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        return self._registry.route(
            path,
            methods=methods,
            name=name,
            referenced=referenced,
            template=template,
            inline=inline,
        )

    def provide(self, annotation: type, factory: Callable[..., Any]) -> None:
        self._registry.provide(annotation, factory)

    def mount_pages(self, pages_dir: str | None = None) -> None:
        self._registry.mount_pages(pages_dir, lazy_pages=self.config.lazy_pages)
        self._sync_aliases()

    def _discover_and_register_pages(self, pages_dir: str) -> None:
        self._registry.discover_and_register_pages(pages_dir)
        self._sync_aliases()

    def register_domain(self, domain: object) -> None:
        self._registry.register_domain(domain)

    def _register_page_handler(
        self,
        *,
        url_path: str,
        handler: Callable[..., Any],
        methods: list[str],
        layout_chain: Any,
        context_providers: tuple[Any, ...],
    ) -> None:
        self._registry.register_page_handler(
            url_path=url_path,
            handler=handler,
            methods=methods,
            layout_chain=layout_chain,
            context_providers=context_providers,
        )
        self._sync_aliases()

    def tool(
        self,
        name: str,
        *,
        description: str = "",
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        return self._registry.tool(name, description=description)

    @property
    def db(self) -> Database:
        if self._mutable_state.db is None:
            msg = (
                "No database configured. Pass db= to App() or use "
                "Database directly: from chirp.data import Database"
            )
            raise RuntimeError(msg)
        return self._mutable_state.db

    @property
    def tools(self) -> Any:
        """The frozen ``ToolRegistry`` — available after ``app.run()`` / freeze.

        Use to inspect registered tools::

            for tool_info in app.tools.list_tools():
                print(tool_info["name"])

        Raises ``RuntimeError`` if accessed before the app is frozen.
        """
        registry = self._runtime_state.tool_registry
        if registry is None:
            msg = "Tool registry is not available until the app is frozen (app.run() or first request)."
            raise RuntimeError(msg)
        return registry

    @property
    def tool_events(self):
        return self._mutable_state.tool_events

    def error(
        self,
        code_or_exception: int | type[Exception],
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        return self._registry.error(code_or_exception)

    def register_oob_region(
        self,
        block_name: str,
        *,
        target_id: str,
        swap: str = "innerHTML",
        wrap: bool = True,
        optional: bool = False,
    ) -> None:
        """Register an OOB region for automatic layout-contract discovery.

        Call during setup (before app.run()). The block_name must match a
        ``{% region <block_name>(...) %}`` in your layout template.

        optional: When True, layouts that omit the block are allowed — the
            region is silently skipped at render time and the orphan-registration
            check downgrades to WARNING. Default False means missing blocks are
            ERRORs at ``app.check()`` and render-time KeyErrors become
            ``BlockNotFoundError`` with a clear message.
        """
        from chirp.templating.oob_registry import OOBRegionConfig

        self._check_not_frozen()
        self._mutable_state.oob_registry.register(
            block_name,
            OOBRegionConfig(
                target_id=target_id,
                swap=swap,
                wrap=wrap,
                optional=optional,
            ),
        )

    def register_fragment_target(
        self,
        target_id: str,
        *,
        fragment_block: str,
        triggers_shell_update: bool = True,
        scope_name: str | None = None,
        omit_outer_layouts: bool = False,
    ) -> None:
        """Register a fragment target for HTMX content-region block selection.

        When HX-Target matches target_id (e.g. ``page-root``), Chirp uses
        fragment_block instead of composition.page_block. Call during setup.

        triggers_shell_update: When True (default), swapping this target triggers
            shell_actions OOB (topbar, breadcrumbs, sidebar). Use False for narrow
            content swaps (e.g. page-content-inner) that should not update the shell.

        scope_name: Optional symbolic scope (e.g. ``"site"``) for hierarchical OOB
            propagation. When set, OOB updates are scoped to this level and above.

        omit_outer_layouts: When True, boosted fragment responses for this target
            skip wrapping with filesystem layouts (page block only). Use for root
            marketing shells whose outlet is the primary ``{% block content %}``
            region so the layout is not nested inside itself on swap.
        """
        self._check_not_frozen()
        self._mutable_state.fragment_target_registry.register(
            target_id,
            fragment_block=fragment_block,
            triggers_shell_update=triggers_shell_update,
            scope_name=scope_name,
            omit_outer_layouts=omit_outer_layouts,
        )

    def register_page_shell_contract(self, contract: PageShellContract) -> None:
        """Register a named page shell contract and its fragment targets.

        This makes app-shell expectations explicit and lets contract checks
        validate required fragment blocks across page templates.
        """
        self._check_not_frozen()
        self._mutable_state.fragment_target_registry.register_contract(contract)

    def register_layout_preset(
        self,
        name: str,
        *,
        target: str | None = None,
        domain_name: str | None = None,
        shell_name: str | None = None,
        swap_scope_name: str | None = None,
        outlet_target_id: str | None = None,
        frame_targets: frozenset[str] | None = None,
        outlet_mode: OutletSwapMode | None = None,
    ) -> None:
        """Register a named preset for `_layout.html` metadata defaults.

        Layouts opt in with ``{# preset: name #}``. Explicit comments in the
        template override preset defaults, letting apps encode a shell
        convention once and keep route-tree metadata terse.
        """
        self._check_not_frozen()
        self._mutable_state.layout_presets[name] = LayoutPreset(
            name=name,
            target=target.lstrip("#") if target is not None else None,
            domain_name=domain_name,
            shell_name=shell_name,
            swap_scope_name=swap_scope_name,
            outlet_target_id=outlet_target_id.lstrip("#") if outlet_target_id is not None else None,
            frame_targets=(
                frozenset(frame.lstrip("#") for frame in frame_targets)
                if frame_targets is not None
                else None
            ),
            outlet_mode=outlet_mode,
        )

    def register_swap_scope(self, scope: str, target_id: str) -> None:
        """Map a symbolic swap scope to a concrete fragment target id (no ``#``).

        Used by :func:`resolve_navigation_swap` and the ``swap_attrs`` template
        global so layouts can declare ``{# swap_scope: name #}`` and links can
        resolve ``hx-target`` from route geometry.
        """
        self._check_not_frozen()
        self._mutable_state.swap_scope_map[scope] = target_id.lstrip("#")

    def get_layout_chain_for_path(self, path: str) -> LayoutChain | None:
        """Return the filesystem :class:`LayoutChain` for a GET route path, if any.

        Uses the compiled router and route table built at freeze time. Unknown
        paths or non-filesystem routes return ``None``.
        """
        from chirp.templating.navigation_swap import lookup_layout_chain_for_path

        self._ensure_frozen()
        return lookup_layout_chain_for_path(
            path,
            router=self._router,
            route_layout_chains=self._runtime_state.route_layout_chains,
        )

    def freeze_params(self, path: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Register a parameter provider for ``chirp freeze``.

        The decorated function must return a list of dicts, each mapping
        parameter names to values.  Example::

            @app.freeze_params("/docs/{slug:path}")
            def docs_params():
                return [{"slug": p.slug} for p in collection.pages]
        """

        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            self._check_not_frozen()
            self._mutable_state.freeze_param_providers[path] = fn
            return fn

        return decorator

    def freeze_exclude(self, path: str) -> None:
        """Exclude a route path from ``chirp freeze``.

        Fragment-only or dynamic routes that should never be written
        as static pages can call this during setup::

            app.freeze_exclude("/docs/search")
        """
        self._check_not_frozen()
        self._mutable_state.freeze_exclude.add(path)

    def live_block(
        self,
        route: str,
        block: str,
        *,
        trigger: str = "load",
        swap: str = "innerHTML",
        skeleton: str | None = None,
        cache_seconds: int | None = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Declare a live block — a template block served dynamically from a frozen page.

        At freeze time the named block is replaced in the emitted HTML with an
        htmx placeholder that fetches from ``/_frag{route}?_b={block}``. At
        request time the block-fetch dispatcher invokes the decorated handler
        and returns only the named block.

        ``route`` must match a registered route; ``block`` must be a named
        block in that route's template. Both are validated at ``app.check()``::

            @app.live_block("/docs/{slug:path}", "recent_updates")
            async def recent_updates(request: Request) -> Fragment:
                return Fragment("docs/page.html", "recent_updates", updates=...)
        """
        self._check_not_frozen()

        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            from chirp.live_blocks import LiveBlockSpec

            self._mutable_state.live_blocks[route, block] = LiveBlockSpec(
                route=route,
                block=block,
                handler=fn,
                trigger=trigger,
                swap=swap,
                skeleton=skeleton,
                cache_seconds=cache_seconds,
            )
            return fn

        return decorator

    def mount(self, prefix: str, plugin: object) -> None:
        """Mount a plugin at the given URL prefix.

        Calls ``plugin.register(app, prefix)`` during setup phase.
        """
        self._check_not_frozen()
        register = getattr(plugin, "register", None)
        if register is None or not callable(register):
            msg = f"Plugin {plugin!r} must have a register(app, prefix) method"
            raise ConfigurationError(msg)
        register(self, prefix)

    def mount_app(self, prefix: str, sub_app: App) -> None:
        """Mount another Chirp :class:`App` at ``prefix``, consuming it.

        Hoists the sub-app's pending routes (prefixed), middleware, lifecycle
        hooks, template globals/filters, and other registrations onto ``self``.
        Parent wins on template-global / filter / error-handler / provider
        collisions (see :mod:`chirp.app.mount` for the full merge matrix).

        After this call, ``sub_app`` is consumed — calling
        ``sub_app.freeze()`` or ``sub_app.run()`` raises ``RuntimeError``. Use
        this during migrations when you need two full apps on one port, not as
        a permanent composition pattern. See ``docs/rfcs/005-mount-app.md``.
        """
        from .mount import hoist, normalize_prefix

        self._check_not_frozen()
        if not isinstance(sub_app, App):
            msg = (
                f"mount_app expected a chirp.App, got {type(sub_app).__name__}. "
                "For plugin-style composition, use app.mount(prefix, plugin) instead."
            )
            raise ConfigurationError(msg)
        if sub_app is self:
            msg = "mount_app cannot mount an app into itself."
            raise ConfigurationError(msg)
        sub_app._check_not_frozen()
        if sub_app._mutable_state.consumed_by_mount_app_prefix is not None:
            msg = (
                f"Sub-app was already consumed by mount_app(prefix="
                f"{sub_app._mutable_state.consumed_by_mount_app_prefix!r}). "
                "Create a fresh App for the new mount point."
            )
            raise ConfigurationError(msg)
        normalized = normalize_prefix(prefix)
        hoist(self._mutable_state, sub_app._mutable_state, normalized)

    def add_loader(self, loader: object) -> None:
        """Add a template loader (e.g., from a plugin's PackageLoader)."""
        self._registry.add_loader(loader)

    def add_middleware(self, middleware: object) -> None:
        self._registry.add_middleware(middleware)

    def add_reload_dir(self, path: str) -> None:
        self._registry.add_reload_dir(path)

    def register_section(self, section: Section) -> None:
        """Register a named section for route metadata resolution."""
        self._registry.register_section(section)

    def register_contract_check(self, check: Callable[..., Any]) -> None:
        """Register a custom contract check that runs during ``app.check()``.

        The callable must accept ``(snapshot, result)`` where *snapshot*
        is a :class:`ContractCheckSnapshot` and *result* is a
        :class:`CheckResult`.  Append issues to ``result.issues``.

        Both plain functions and callable class instances are accepted.
        """
        self._check_not_frozen()
        if not callable(check):
            msg = f"Contract check must be callable, got {type(check).__name__}"
            raise TypeError(msg)
        self._mutable_state.contract_checks.append(check)

    def set_contract_check_data(self, key: str, value: Any) -> None:
        """Store arbitrary data for use by custom contract checks.

        Data is available in ``snapshot.extras[key]`` during
        ``app.check()``.
        """
        self._check_not_frozen()
        self._mutable_state.contract_check_data[key] = value

    def override_contract_severity(self, category: str, severity: Severity) -> None:
        """Override the severity of all contract issues in *category*.

        Applied as a post-processing step after all checks (built-in and
        custom) have run.  For example, to promote dead-template warnings
        to errors::

            app.override_contract_severity("dead", Severity.ERROR)
        """
        self._check_not_frozen()
        if not isinstance(severity, Severity):
            msg = f"severity must be a Severity enum member, got {type(severity).__name__}"
            raise TypeError(msg)
        self._mutable_state.contract_severity_overrides[category] = severity

    def template_filter(
        self,
        name: str | None = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        return self._registry.template_filter(name)

    def template_global(
        self,
        name: str | None = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        return self._registry.template_global(name)

    def url_for(self, name: str, /, **params: Any) -> str:
        """Reverse a named route to a URL path.

        Path-param kwargs substitute into ``{braces}`` and are percent-encoded;
        any leftover kwargs become a urlencoded query string.

        Raises ``LookupError`` when ``name`` is not registered (the message
        lists every known name) and ``KeyError`` when a required path param
        is missing. Also registered as the ``url_for`` template global.
        """
        from chirp.app.url_for import resolve_url

        self._ensure_frozen()
        return resolve_url(self._runtime_state.routes_by_name or {}, name, **params)

    def on_startup(self, func: Callable[..., Any]) -> Callable[..., Any]:
        return self._registry.on_startup(func)

    def on_shutdown(self, func: Callable[..., Any]) -> Callable[..., Any]:
        return self._registry.on_shutdown(func)

    def on_worker_startup(self, func: Callable[..., Any]) -> Callable[..., Any]:
        return self._registry.on_worker_startup(func)

    def on_worker_shutdown(self, func: Callable[..., Any]) -> Callable[..., Any]:
        return self._registry.on_worker_shutdown(func)

    def run(
        self,
        host: str | None = None,
        port: int | None = None,
        *,
        lifecycle_collector: LifecycleCollector | None = None,
    ) -> None:
        """Freeze the app and start the development server.

        In debug mode, freeze runs the full hypermedia contract suite
        (routes, fragment targets, OOB regions, htmx attrs, SSE wiring,
        layouts, alpine CDN, defer_falsy, composition_extends, plus any
        registered custom checks) and prints a colored banner to stderr.
        An ERROR-severity issue exits before the server starts. Disable
        with ``AppConfig(skip_contract_checks=True)`` or
        ``CHIRP_SKIP_CONTRACT_CHECKS=1``.
        """
        self._ensure_frozen()
        self._server.run(
            self,
            host=host,
            port=port,
            lifecycle_collector=lifecycle_collector,
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self._runtime.handle(scope, receive, send)

    def handle_sync(self, raw: object) -> object | None:
        """Fused sync path — bypass ASGI for simple request-response handlers.

        Returns RawResponse for sync handling, or None to fall through to ASGI.
        """
        from pounce.sync_protocol import RawRequest

        self._ensure_frozen()
        if self._router is None:
            return None
        from chirp.server.sync_handler import handle_sync as _handle_sync

        return _handle_sync(
            raw=raw,  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]
            router=self._router,
            middleware=self._middleware,
            providers=self._mutable_state.providers,
        )

    async def _handle_lifespan(self, scope: Scope, receive: Receive, send: Send) -> None:
        await self._lifecycle.handle_lifespan(scope, receive, send)

    async def _handle_worker_startup(self) -> None:
        await self._lifecycle.handle_worker_startup()

    async def _handle_worker_shutdown(self) -> None:
        await self._lifecycle.handle_worker_shutdown()

    def freeze(self) -> None:
        """Freeze the app, finalizing all configuration.

        Idempotent — safe to call multiple times.  After freezing, no
        further routes, middleware, or plugins can be registered.

        In debug mode, freeze also runs the hypermedia contract checks
        and exits on ERROR (same suite as ``app.check()``). Disable with
        ``AppConfig(skip_contract_checks=True)`` or the
        ``CHIRP_SKIP_CONTRACT_CHECKS`` env var.

        Useful in tests and CI to call ``app.check()`` without starting
        a server::

            app.freeze()
            app.check()
        """
        self._ensure_frozen()

    def _ensure_frozen(self) -> None:
        if self._runtime_state.frozen:
            return
        consumed_prefix = self._mutable_state.consumed_by_mount_app_prefix
        if consumed_prefix is not None:
            msg = (
                f"This App was consumed by mount_app(prefix={consumed_prefix!r}) "
                "and cannot be frozen or run independently. Serve requests through "
                "the parent app, or remove the mount_app call to keep this app standalone."
            )
            raise RuntimeError(msg)
        with self._freeze_lock:
            if self._runtime_state.frozen:
                return
            self._freeze()

    def _freeze(self) -> None:
        self._compiler.freeze(
            self,
            lambda: self._run_debug_checks(),
            self._sync_runtime_aliases,
        )
        self._sync_runtime_aliases()

    def _run_debug_checks(self) -> None:
        self._assert_contracts_ready()
        self._contract_checks.run_debug_checks(self)

    def check(self, *, warnings_as_errors: bool = False, coverage: bool = False) -> None:
        """Validate hypermedia contracts against the frozen app and print a report.

        Runs every registered contract check (routes, fragment targets, OOB
        regions, htmx attributes, SSE wiring, accessibility, layout chains, plus
        any custom checks added via :meth:`register_contract_check`) and writes
        a colored report to stdout.

        Intended use: call from CI or a startup script. ``chirp check <app>``
        wraps this method.

        Args:
            warnings_as_errors: When True, WARNING-severity issues fail the
                check alongside errors (use this in CI to fail on drift).
            coverage: When True, include contract coverage counters for POST
                form contracts, mounted page contracts, app-shell targets, and
                OOB regions.

        Raises:
            SystemExit: With code 1 when any ERROR issue is found, or any
                WARNING when ``warnings_as_errors=True``.
            RuntimeError: If called before :meth:`freeze` (the app must be
                frozen to expose the snapshot checks read).
        """
        self._ensure_frozen()
        self._assert_contracts_ready()
        self._contract_checks.check(
            self,
            warnings_as_errors=warnings_as_errors,
            coverage=coverage,
        )

    def render(self, value: Fragment | Template | InlineTemplate) -> str:
        """Render a Fragment, Template, or InlineTemplate to HTML without an HTTP request.

        Use for tests, background jobs, scripts, or AI runtimes that need to
        produce HTML from the app's templates.

        Raises:
            ConfigurationError: If kida_env is not configured (Fragment/Template
                require template_dir or custom kida_env).
        """
        self._ensure_frozen()
        env = self._runtime_state.kida_env
        if isinstance(value, InlineTemplate):
            if env is None:
                env = Environment()
            return env.from_string(value.source).render(value.context)
        if env is None:
            msg = (
                "Fragment/Template return types require kida integration. "
                "Ensure a template_dir is configured in AppConfig."
            )
            raise ConfigurationError(msg)
        if isinstance(value, Fragment):
            return render_fragment(env, value)
        return render_template(env, value)

    def _check_not_frozen(self) -> None:
        if self._runtime_state.frozen:
            msg = (
                "Cannot modify the app after it has started serving requests. "
                "Register routes, middleware, and filters before calling app.run()."
            )
            raise RuntimeError(msg)

    def _assert_contracts_ready(self) -> None:
        if self._runtime_state.contracts_ready:
            return
        msg = (
            "Contract checks ran before runtime state was ready. "
            "Ensure freeze publishes router/env before checks."
        )
        raise RuntimeError(msg)

    def _contract_check_snapshot(self) -> ContractCheckSnapshot:
        self._ensure_frozen()
        self._assert_contracts_ready()
        assert self._runtime_state.router is not None
        kida_env = self._runtime_state.kida_env
        ts: dict[str, str] = {}
        if kida_env is not None and kida_env.loader is not None:
            from chirp.contracts.template_scan import load_template_sources

            ts = load_template_sources(kida_env)
        return ContractCheckSnapshot(
            router=self._runtime_state.router,
            kida_env=kida_env,
            layout_chains=self._mutable_state.discovered_layout_chains,
            page_route_paths=self._mutable_state.page_route_paths,
            page_leaf_templates=self._mutable_state.page_leaf_templates,
            page_templates=self._mutable_state.page_templates,
            fragment_target_registry=self._mutable_state.fragment_target_registry,
            islands_contract_strict=self.config.islands_contract_strict,
            oob_registry=self._runtime_state.oob_registry,
            sections=self._mutable_state.sections,
            route_metas=self._mutable_state.route_metas,
            route_templates=self._mutable_state.route_templates,
            discovered_routes=self._mutable_state.discovered_routes,
            page_handler_findings=list(self._mutable_state.page_handler_findings),
            route_name_collisions=dict(self._runtime_state.route_name_collisions),
            mount_app_skips=list(self._mutable_state.mount_app_skips),
            template_sources=ts,
            extras=dict(self._mutable_state.contract_check_data),
        )
