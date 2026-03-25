"""Chirp application facade."""

import threading
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from kida import Environment

from chirp._internal.asgi import Receive, Scope, Send
from chirp.config import AppConfig
from chirp.errors import ConfigurationError
from chirp.pages.types import Section
from chirp.templating.fragment_target_registry import PageShellContract
from chirp.templating.integration import render_fragment, render_template
from chirp.templating.returns import Fragment, InlineTemplate, Template

from .compiler import AppCompiler
from .diagnostics import ContractCheckRunner
from .lifecycle import LifecycleCoordinator
from .registry import AppRegistry
from .runtime import ASGIRuntime
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
    ) -> None:
        """Register an OOB region for automatic layout-contract discovery.

        Call during setup (before app.run()). The block_name must match a
        ``{% region <block_name>(...) %}`` in your layout template.
        """
        from chirp.templating.oob_registry import OOBRegionConfig

        self._check_not_frozen()
        self._mutable_state.oob_registry.register(
            block_name,
            OOBRegionConfig(target_id=target_id, swap=swap, wrap=wrap),
        )

    def register_fragment_target(
        self,
        target_id: str,
        *,
        fragment_block: str,
        triggers_shell_update: bool = True,
    ) -> None:
        """Register a fragment target for HTMX content-region block selection.

        When HX-Target matches target_id (e.g. ``page-root``), Chirp uses
        fragment_block instead of composition.page_block. Call during setup.

        triggers_shell_update: When True (default), swapping this target triggers
            shell_actions OOB (topbar, breadcrumbs, sidebar). Use False for narrow
            content swaps (e.g. page-content-inner) that should not update the shell.
        """
        self._check_not_frozen()
        self._mutable_state.fragment_target_registry.register(
            target_id,
            fragment_block=fragment_block,
            triggers_shell_update=triggers_shell_update,
        )

    def register_page_shell_contract(self, contract: PageShellContract) -> None:
        """Register a named page shell contract and its fragment targets.

        This makes app-shell expectations explicit and lets contract checks
        validate required fragment blocks across page templates.
        """
        self._check_not_frozen()
        self._mutable_state.fragment_target_registry.register_contract(contract)

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
            raw=raw,  # type: ignore[arg-type]
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

    def _ensure_frozen(self) -> None:
        if self._runtime_state.frozen:
            return
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

    def check(self, *, warnings_as_errors: bool = False) -> None:
        self._ensure_frozen()
        self._assert_contracts_ready()
        self._contract_checks.check(self, warnings_as_errors=warnings_as_errors)

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
        return ContractCheckSnapshot(
            router=self._runtime_state.router,
            kida_env=self._runtime_state.kida_env,
            layout_chains=self._mutable_state.discovered_layout_chains,
            page_route_paths=self._mutable_state.page_route_paths,
            page_leaf_templates=self._mutable_state.page_leaf_templates,
            page_templates=self._mutable_state.page_templates,
            fragment_target_registry=self._mutable_state.fragment_target_registry,
            islands_contract_strict=self.config.islands_contract_strict,
            sections=self._mutable_state.sections,
            route_metas=self._mutable_state.route_metas,
            route_templates=self._mutable_state.route_templates,
            discovered_routes=self._mutable_state.discovered_routes,
        )
