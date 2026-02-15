"""Chirp application class.

Mutable during setup (route registration, middleware, filters, tools).
Frozen at runtime when app.run() or __call__() is first invoked.
"""

import inspect
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from kida import Environment

from chirp._internal.asgi import Receive, Scope, Send
from chirp._internal.types import ErrorHandler, Handler
from chirp.config import AppConfig
from chirp.http.request import Request
from chirp.middleware.protocol import Middleware
from chirp.routing.route import Route
from chirp.routing.router import Router
from chirp.server.handler import handle_request
from chirp.templating.integration import create_environment
from chirp.tools.events import ToolEventBus
from chirp.tools.registry import ToolRegistry, compile_tools

if TYPE_CHECKING:
    from chirp.data.database import Database


@dataclass(slots=True)
class _PendingRoute:
    """A route waiting to be compiled."""

    path: str
    handler: Handler
    methods: list[str] | None
    name: str | None
    referenced: bool = False
    template: str | None = None


@dataclass(slots=True)
class _PendingTool:
    """A tool waiting to be compiled."""

    name: str
    description: str
    handler: Callable[..., Any]


class App:
    """The chirp application.

    Mutable during setup (route registration, middleware, filters).
    Frozen at runtime when ``app.run()`` or ``__call__()`` is first invoked.

    Thread safety:
        The setup phase is single-threaded (decorators at import time).
        The freeze transition uses a Lock + double-check to ensure exactly
        one thread compiles the app, even under free-threading where
        multiple ASGI workers could call ``__call__()`` concurrently on
        first request.
    """

    __slots__ = (
        "_custom_kida_env",
        "_db",
        "_error_handlers",
        "_freeze_lock",
        "_frozen",
        "_kida_env",
        "_middleware",
        "_middleware_list",
        "_migrations_dir",
        # Page convention metadata (populated by mount_pages)
        "_page_route_paths",
        "_page_templates",
        "_pending_routes",
        "_pending_tools",
        # Service injection via providers
        "_providers",
        # Compiled state (populated by _freeze)
        "_router",
        "_shutdown_hooks",
        "_startup_hooks",
        "_template_filters",
        "_template_globals",
        # Tool support (MCP)
        "_tool_events",
        "_tool_registry",
        # Per-worker lifecycle hooks (run on each worker's event loop)
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
        self.config: AppConfig = config or AppConfig()
        self._pending_routes: list[_PendingRoute] = []
        self._pending_tools: list[_PendingTool] = []
        self._middleware_list: list[Middleware] = []
        self._error_handlers: dict[int | type, ErrorHandler] = {}
        self._template_filters: dict[str, Callable[..., Any]] = {}
        self._template_globals: dict[str, Any] = {}
        self._startup_hooks: list[Callable[..., Any]] = []
        self._shutdown_hooks: list[Callable[..., Any]] = []
        self._worker_startup_hooks: list[Callable[..., Any]] = []
        self._worker_shutdown_hooks: list[Callable[..., Any]] = []
        self._page_route_paths: set[str] = set()
        self._page_templates: set[str] = set()
        self._providers: dict[type, Callable[..., Any]] = {}
        self._frozen: bool = False
        self._freeze_lock: threading.Lock = threading.Lock()
        self._custom_kida_env: Environment | None = kida_env  # User-provided kida environment

        # Database — accepts a Database instance or connection URL string.
        # When set, lifecycle hooks are auto-registered for connect/disconnect.
        if isinstance(db, str):
            from chirp.data.database import Database as _Database

            self._db: Database | None = _Database(db)
        else:
            self._db = db

        # Migrations directory — when set with db, migrations run at startup.
        self._migrations_dir: str | None = migrations

        # Tool event bus — created eagerly so subscribers can register
        # before freeze. The bus itself is thread-safe.
        self._tool_events: ToolEventBus = ToolEventBus()

        # Compiled state — set during _freeze()
        self._router: Router | None = None
        self._middleware: tuple[Callable[..., Any], ...] = ()
        self._kida_env: Environment | None = None
        self._tool_registry: ToolRegistry | None = None

    # -- Route registration --

    def route(
        self,
        path: str,
        *,
        methods: list[str] | None = None,
        name: str | None = None,
        referenced: bool = False,
        template: str | None = None,
    ) -> Callable[[Handler], Handler]:
        """Register a route handler via decorator.

        Args:
            path: URL path pattern. Use ``{param}`` for path parameters.
            methods: HTTP methods. Defaults to ``["GET"]``.
            name: Optional route name for URL generation.
            referenced: If True, ``chirp check`` will not flag this route as
                orphan when it is not referenced from templates. Use for
                dynamic routes (e.g. ``/share/{slug}``, ``/ask/stream``).
            template: Template name this route renders (e.g. ``"index.html"``).
                Used by ``chirp check`` to avoid false-positive dead-template
                warnings for routes that return ``Template(...)`` without
                ``@contract``.
        """

        def decorator(func: Handler) -> Handler:
            self._check_not_frozen()
            self._pending_routes.append(
                _PendingRoute(path, func, methods, name, referenced, template)
            )
            return func

        return decorator

    # -- Service injection --

    def provide(self, annotation: type, factory: Callable[..., Any]) -> None:
        """Register a provider factory for dependency injection.

        When a handler parameter's type annotation matches *annotation*,
        chirp calls *factory* (with no arguments) and injects the result.

        Works for both ``@app.route`` and filesystem page handlers::

            app.provide(DocumentStore, get_store)

            # Any handler with ``store: DocumentStore`` gets it injected:
            def get(store: DocumentStore) -> Page: ...

        Args:
            annotation: The type annotation to match against handler params.
            factory: A zero-argument callable that returns the service instance.
        """
        self._check_not_frozen()
        self._providers[annotation] = factory

    # -- Filesystem page routing --

    def mount_pages(self, pages_dir: str | None = None) -> None:
        """Mount a filesystem-based pages directory.

        Walks the directory and registers routes for every ``page.py``
        and handler ``.py`` file, with automatic layout nesting and
        context cascade.

        ``_layout.html`` files define shells with ``{% block content %}``
        and ``{# target: element_id #}`` declarations.
        ``_context.py`` files provide shared context that cascades
        from parent directories to children.

        Args:
            pages_dir: Path to the pages directory.  Defaults to
                ``"pages"`` relative to the working directory.

        Example::

            app = App(AppConfig(template_dir="pages"))
            app.mount_pages("pages")
        """
        from chirp.pages.discovery import discover_pages
        from chirp.pages.types import ContextProvider, LayoutChain

        self._check_not_frozen()

        pages_dir = pages_dir or "pages"
        page_routes = discover_pages(pages_dir)

        # Record page convention metadata for contract checking.
        # Page routes are navigated to directly (browser URL bar, JS fetch)
        # and their sibling templates are rendered implicitly — the checker
        # uses this to suppress false-positive orphan/dead warnings.
        for page_route in page_routes:
            self._page_route_paths.add(page_route.url_path)
            if page_route.template_name:
                self._page_templates.add(page_route.template_name)
            for layout in page_route.layout_chain.layouts:
                self._page_templates.add(layout.template_name)

        for page_route in page_routes:
            # Capture route metadata in closure
            original_handler = page_route.handler
            chain = page_route.layout_chain
            providers = page_route.context_providers

            # Wrap handler to inject cascade context and return LayoutPage
            self._register_page_handler(
                url_path=page_route.url_path,
                handler=original_handler,
                methods=list(page_route.methods),
                layout_chain=chain,
                context_providers=providers,
            )

    def _register_page_handler(
        self,
        *,
        url_path: str,
        handler: Callable[..., Any],
        methods: list[str],
        layout_chain: Any,
        context_providers: tuple[Any, ...],
    ) -> None:
        """Register a single page handler with cascade context wrapper."""
        from chirp._internal.invoke import invoke
        from chirp.pages.context import build_cascade_context
        from chirp.pages.resolve import resolve_kwargs, upgrade_result

        _handler = handler
        _chain = layout_chain
        _providers = context_providers
        _service_providers = self._providers

        async def page_wrapper(request: Request) -> Any:
            """Wrapper that runs context cascade and upgrades Page → LayoutPage."""
            cascade_ctx = await build_cascade_context(
                _providers, request.path_params
            )
            kwargs = await resolve_kwargs(
                _handler, request, cascade_ctx, _service_providers
            )
            result = await invoke(_handler, **kwargs)
            return upgrade_result(result, cascade_ctx, _chain, _providers)

        self._pending_routes.append(
            _PendingRoute(url_path, page_wrapper, methods, name=None, referenced=False)
        )

    # -- Tool registration --

    def tool(
        self,
        name: str,
        *,
        description: str = "",
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Register a function as an MCP tool via decorator.

        The tool is callable by MCP clients via JSON-RPC at ``/mcp``
        and can also be called directly from route handlers as a
        normal Python function.

        Tool calls emit ``ToolCallEvent`` to ``app.tool_events``
        for real-time dashboard subscriptions.

        Usage::

            @app.tool("search", description="Search inventory")
            async def search(query: str, category: str | None = None) -> list[dict]:
                return await db.search(query, category=category)
        """

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self._check_not_frozen()
            self._pending_tools.append(_PendingTool(name, description, func))
            return func

        return decorator

    @property
    def db(self) -> Database:
        """The database instance, if configured.

        Raises ``RuntimeError`` if no database was configured on this app.

        Usage::

            app = App(db="sqlite:///app.db")

            @app.route("/users")
            async def users():
                return await app.db.fetch(User, "SELECT * FROM users")
        """
        if self._db is None:
            msg = (
                "No database configured. Pass db= to App() or use "
                "Database directly: from chirp.data import Database"
            )
            raise RuntimeError(msg)
        return self._db

    @property
    def tool_events(self) -> ToolEventBus:
        """Public access to the tool event bus for SSE subscriptions.

        Usage::

            @app.route("/dashboard/feed")
            async def feed(request: Request):
                async def stream():
                    async for event in app.tool_events.subscribe():
                        yield Fragment("dashboard.html", "row", event=event)
                return EventStream(stream())
        """
        return self._tool_events

    # -- Error handlers --

    def error(
        self,
        code_or_exception: int | type[Exception],
    ) -> Callable[[ErrorHandler], ErrorHandler]:
        """Register an error handler via decorator."""

        def decorator(func: ErrorHandler) -> ErrorHandler:
            self._check_not_frozen()
            self._error_handlers[code_or_exception] = func
            return func

        return decorator

    # -- Middleware --

    def add_middleware(self, middleware: Middleware) -> None:
        """Add a middleware to the pipeline."""
        self._check_not_frozen()
        self._middleware_list.append(middleware)

    # -- Template integration --

    def template_filter(
        self,
        name: str | None = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Register a kida template filter."""

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self._check_not_frozen()
            filter_name = name or func.__name__
            self._template_filters[filter_name] = func
            return func

        return decorator

    def template_global(
        self,
        name: str | None = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Register a kida template global."""

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self._check_not_frozen()
            global_name = name or func.__name__
            self._template_globals[global_name] = func
            return func

        return decorator

    # -- Lifecycle hooks --

    def on_startup(self, func: Callable[..., Any]) -> Callable[..., Any]:
        """Register an async or sync startup hook via decorator.

        Hooks run in registration order during ASGI lifespan startup,
        before the server begins accepting HTTP requests.

        Usage::

            @app.on_startup
            async def setup():
                await db.connect()
        """
        self._check_not_frozen()
        self._startup_hooks.append(func)
        return func

    def on_shutdown(self, func: Callable[..., Any]) -> Callable[..., Any]:
        """Register an async or sync shutdown hook via decorator.

        Hooks run in registration order during ASGI lifespan shutdown,
        after the server stops accepting new requests.

        Usage::

            @app.on_shutdown
            async def teardown():
                await db.disconnect()
        """
        self._check_not_frozen()
        self._shutdown_hooks.append(func)
        return func

    def on_worker_startup(self, func: Callable[..., Any]) -> Callable[..., Any]:
        """Register a per-worker startup hook via decorator.

        Unlike ``on_startup`` (which runs once during ASGI lifespan),
        this hook runs **on each worker's event loop** before that worker
        begins accepting connections.  Use this for async resources that
        bind to the event loop (httpx clients, DB connection pools, etc.).

        Requires a server that sends ``pounce.worker.startup`` scopes
        (e.g. pounce).  Under other servers, the hooks simply never fire.

        Usage::

            @app.on_worker_startup
            async def create_client():
                _client_var.set(httpx.AsyncClient(...))
        """
        self._check_not_frozen()
        self._worker_startup_hooks.append(func)
        return func

    def on_worker_shutdown(self, func: Callable[..., Any]) -> Callable[..., Any]:
        """Register a per-worker shutdown hook via decorator.

        Runs **on each worker's event loop** after that worker stops
        accepting connections.  Pair with ``on_worker_startup`` for
        per-worker resource cleanup.

        Usage::

            @app.on_worker_shutdown
            async def close_client():
                client = _client_var.get(None)
                if client:
                    await client.aclose()
        """
        self._check_not_frozen()
        self._worker_shutdown_hooks.append(func)
        return func

    # -- Server --

    def run(
        self,
        host: str | None = None,
        port: int | None = None,
        *,
        lifecycle_collector: object | None = None,
    ) -> None:
        """Start the server (dev or production based on config.debug).

        Compiles the app (freezing routes, middleware, templates)
        and starts serving requests.

        - **Development mode** (debug=True): Single worker with auto-reload
        - **Production mode** (debug=False): Multi-worker with Phase 5 & 6 features

        Args:
            host: Override bind host.
            port: Override bind port.
            lifecycle_collector: Optional Pounce LifecycleCollector for
                observability.  Forwarded to the Pounce Server.

        """
        self._ensure_frozen()

        _host = host or self.config.host
        _port = port or self.config.port

        if self.config.debug:
            # Development mode (existing behavior)
            from chirp.server.dev import run_dev_server

            run_dev_server(
                self,
                _host,
                _port,
                reload=self.config.debug,
                reload_include=self.config.reload_include,
                reload_dirs=self.config.reload_dirs,
                lifecycle_collector=lifecycle_collector,
            )
        else:
            # Production mode (new!)
            from chirp.server.production import run_production_server

            run_production_server(
                self,
                host=_host,
                port=_port,
                workers=self.config.workers,
                # Phase 6.1: Prometheus Metrics
                metrics_enabled=self.config.metrics_enabled,
                metrics_path=self.config.metrics_path,
                # Phase 6.2: Rate Limiting
                rate_limit_enabled=self.config.rate_limit_enabled,
                rate_limit_requests_per_second=self.config.rate_limit_requests_per_second,
                rate_limit_burst=self.config.rate_limit_burst,
                # Phase 6.3: Request Queueing
                request_queue_enabled=self.config.request_queue_enabled,
                request_queue_max_depth=self.config.request_queue_max_depth,
                # Phase 6.4: Sentry Error Tracking
                sentry_dsn=self.config.sentry_dsn,
                sentry_environment=self.config.sentry_environment,
                sentry_release=self.config.sentry_release,
                sentry_traces_sample_rate=self.config.sentry_traces_sample_rate,
                # Phase 6.5: Hot Reload
                reload_timeout=self.config.reload_timeout,
                # Phase 5: OpenTelemetry
                otel_endpoint=self.config.otel_endpoint,
                otel_service_name=self.config.otel_service_name,
                # Phase 5: WebSocket
                websocket_compression=self.config.websocket_compression,
                websocket_max_message_size=self.config.websocket_max_message_size,
                # Production settings
                lifecycle_logging=self.config.lifecycle_logging,
                log_format=self.config.log_format,
                log_level=self.config.log_level,
                max_connections=self.config.max_connections,
                backlog=self.config.backlog,
                keep_alive_timeout=self.config.keep_alive_timeout,
                request_timeout=self.config.request_timeout,
                # TLS
                ssl_certfile=self.config.ssl_certfile,
                ssl_keyfile=self.config.ssl_keyfile,
            )

    # -- ASGI interface --

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ASGI 3.0 entry point.

        Handles lifespan and per-worker lifecycle scopes directly,
        then delegates HTTP scopes to the request handler pipeline.
        """
        if scope["type"] == "lifespan":
            await self._handle_lifespan(scope, receive, send)
            return

        if scope["type"] == "pounce.worker.startup":
            await self._handle_worker_startup()
            return

        if scope["type"] == "pounce.worker.shutdown":
            await self._handle_worker_shutdown()
            return

        self._ensure_frozen()

        assert self._router is not None

        await handle_request(
            scope,
            receive,
            send,
            router=self._router,
            middleware=self._middleware,
            error_handlers=self._error_handlers,
            kida_env=self._kida_env,
            debug=self.config.debug,
            providers=self._providers or None,
            tool_registry=self._tool_registry,
            mcp_path=self.config.mcp_path,
            sse_heartbeat_interval=self.config.sse_heartbeat_interval,
            sse_retry_ms=self.config.sse_retry_ms,
            sse_close_event=self.config.sse_close_event,
        )

    async def _handle_lifespan(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        """Run the ASGI lifespan protocol.

        Freezes the app at startup (before first HTTP request), then
        runs registered startup/shutdown hooks and signals completion
        back to the server.
        """
        self._ensure_frozen()

        while True:
            message = await receive()
            msg_type = message["type"]

            if msg_type == "lifespan.startup":
                try:
                    # Auto-connect database if configured
                    if self._db is not None:
                        await self._db.connect()
                        from chirp.data.database import _db_var

                        _db_var.set(self._db)

                        # Run migrations if a directory is configured
                        if self._migrations_dir is not None:
                            from chirp.data.migrate import migrate

                            await migrate(self._db, self._migrations_dir)

                    for hook in self._startup_hooks:
                        result = hook()
                        if inspect.isawaitable(result):
                            await result
                    await send({"type": "lifespan.startup.complete"})
                except Exception as exc:
                    await send(
                        {
                            "type": "lifespan.startup.failed",
                            "message": str(exc),
                        }
                    )
                    return

            elif msg_type == "lifespan.shutdown":
                for hook in self._shutdown_hooks:
                    result = hook()
                    if inspect.isawaitable(result):
                        await result

                # Auto-disconnect database if configured
                if self._db is not None:
                    await self._db.disconnect()

                # Close tool event bus so SSE subscribers disconnect cleanly
                self._tool_events.close()
                await send({"type": "lifespan.shutdown.complete"})
                return

    # -- Per-worker lifecycle --

    async def _handle_worker_startup(self) -> None:
        """Run registered per-worker startup hooks.

        Called by pounce when a worker thread starts, on that worker's
        event loop.  Errors propagate to pounce, which prevents the
        worker from accepting connections.
        """
        for hook in self._worker_startup_hooks:
            result = hook()
            if inspect.isawaitable(result):
                await result

    async def _handle_worker_shutdown(self) -> None:
        """Run registered per-worker shutdown hooks.

        Called by pounce when a worker thread stops, on that worker's
        event loop.  Errors propagate to pounce, which logs and
        continues shutdown.
        """
        for hook in self._worker_shutdown_hooks:
            result = hook()
            if inspect.isawaitable(result):
                await result

    # -- Internal --

    def _ensure_frozen(self) -> None:
        """Thread-safe freeze with double-check locking.

        Under free-threading (3.14t), multiple ASGI worker threads could
        call __call__() concurrently on first request. This pattern ensures
        exactly one thread performs compilation.
        """
        if self._frozen:
            return
        with self._freeze_lock:
            if self._frozen:
                return
            self._freeze()

    def _freeze(self) -> None:
        """Compile the app into its frozen runtime state.

        MUST only be called while holding _freeze_lock.
        """
        # 1. Compile route table
        router = Router()
        for pending in self._pending_routes:
            methods = frozenset(m.upper() for m in (pending.methods or ["GET"]))
            route = Route(
                path=pending.path,
                handler=pending.handler,
                methods=methods,
                name=pending.name,
                referenced=pending.referenced,
                template=pending.template,
            )
            router.add(route)
        router.compile()
        self._router = router

        # 2. Capture middleware as immutable tuple — append auto-injected
        #    snippets so the developer doesn't have to wire them up manually.
        middleware_list = list(self._middleware_list)

        #    Safe target: auto-add hx-target="this" to event-driven elements
        #    that would otherwise inherit the layout target.  Always-on by
        #    default; disable with AppConfig(safe_target=False).
        if self.config.safe_target:
            from chirp.middleware.inject import HTMLInject
            from chirp.server.htmx_safe_target import SAFE_TARGET_SNIPPET

            middleware_list.append(
                HTMLInject(SAFE_TARGET_SNIPPET, full_page_only=True)
            )

        #    SSE lifecycle: data-sse-state attribute + custom events on
        #    [sse-connect] elements.  Enabled by default.
        if self.config.sse_lifecycle:
            from chirp.middleware.inject import HTMLInject
            from chirp.server.sse_lifecycle import SSE_LIFECYCLE_SNIPPET

            middleware_list.append(
                HTMLInject(SSE_LIFECYCLE_SNIPPET, full_page_only=True)
            )

        #    Event delegation: copy-btn, compare-switch for SSE-swapped content.
        if self.config.delegation:
            from chirp.middleware.inject import HTMLInject
            from chirp.server.delegation import DELEGATION_SNIPPET

            middleware_list.append(
                HTMLInject(DELEGATION_SNIPPET, full_page_only=True)
            )

        #    View Transitions: meta tag + CSS defaults + htmx global config.
        #    Opt-in (default False) — changes visual behavior.
        if self.config.view_transitions:
            from chirp.middleware.inject import HTMLInject
            from chirp.server.view_transitions import (
                VIEW_TRANSITIONS_HEAD_SNIPPET,
                VIEW_TRANSITIONS_SCRIPT_SNIPPET,
            )

            middleware_list.append(
                HTMLInject(
                    VIEW_TRANSITIONS_HEAD_SNIPPET,
                    before="</head>",
                    full_page_only=True,
                )
            )
            middleware_list.append(
                HTMLInject(VIEW_TRANSITIONS_SCRIPT_SNIPPET, full_page_only=True)
            )

        #    Debug overlays (htmx error toasts, etc.) — debug mode only.
        if self.config.debug:
            from chirp.middleware.inject import HTMLInject
            from chirp.server.htmx_debug import HTMX_DEBUG_BOOT_SNIPPET

            middleware_list.append(HTMLInject(HTMX_DEBUG_BOOT_SNIPPET))
        self._middleware = tuple(middleware_list)

        # 2b. Collect template globals from middleware
        # Middleware can define a `template_globals` dict attribute to
        # auto-register template globals (e.g. AuthMiddleware → current_user).
        for mw in self._middleware:
            mw_globals = getattr(mw, "template_globals", None)
            if mw_globals and isinstance(mw_globals, dict):
                for name, func in mw_globals.items():
                    self._template_globals.setdefault(name, func)

        # 3. Initialize kida environment
        # Use custom environment if provided, otherwise create from config
        if self._custom_kida_env is not None:
            self._kida_env = self._custom_kida_env
            # Apply user filters and globals to custom env
            if self._template_filters:
                self._kida_env.update_filters(self._template_filters)
            for name, value in self._template_globals.items():
                self._kida_env.add_global(name, value)
        else:
            self._kida_env = create_environment(
                self.config,
                self._template_filters,
                self._template_globals,
            )

        # 4. Compile tool registry (schema generation happens here so
        #    errors surface at startup, not at runtime)
        self._tool_registry = compile_tools(
            [(t.name, t.description, t.handler) for t in self._pending_tools],
            self._tool_events,
        )

        self._frozen = True

        # 5. Auto-validate hypermedia surface in debug mode.
        #    Prints warnings to the terminal at startup so the developer
        #    sees broken hx-target selectors, missing routes, and
        #    accessibility issues before opening a browser.
        #    Warnings only — never blocks startup (false positives are
        #    possible for dynamic IDs).
        if self.config.debug:
            self._run_debug_checks()

    def _run_debug_checks(self) -> None:
        """Run contract checks and print results to stderr.

        Uses the rich terminal formatter so output matches the pounce
        startup banner's visual language.  Printed even when there are
        no issues (confirms checks ran).  Exits with non-zero if any
        Severity.ERROR issues exist, so developers fix sse_scope
        violations before opening the browser.
        """
        import sys

        from chirp.contracts import check_hypermedia_surface
        from chirp.server.terminal_checks import format_check_result

        result = check_hypermedia_surface(self)
        sys.stderr.write(format_check_result(result))
        if not result.ok:
            sys.exit(1)

    def check(self) -> None:
        """Validate the hypermedia surface and print results.

        Freezes the app if needed, then checks that every htmx target,
        form action, and fragment contract resolves to a valid route.
        Raises ``SystemExit(1)`` if errors are found.

        Usage::

            app.check()  # prints results and exits on errors

        """
        from chirp.contracts import check_hypermedia_surface
        from chirp.server.terminal_checks import format_check_result

        result = check_hypermedia_surface(self)
        print(format_check_result(result, color=None))
        if not result.ok:
            raise SystemExit(1)

    def _check_not_frozen(self) -> None:
        if self._frozen:
            msg = (
                "Cannot modify the app after it has started serving requests. "
                "Register routes, middleware, and filters before calling app.run()."
            )
            raise RuntimeError(msg)
