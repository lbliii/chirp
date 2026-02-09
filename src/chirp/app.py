"""Chirp application class.

Mutable during setup (route registration, middleware, filters, tools).
Frozen at runtime when app.run() or __call__() is first invoked.
"""

from __future__ import annotations

import inspect
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from kida import Environment

from chirp._internal.asgi import Receive, Scope, Send
from chirp._internal.types import ErrorHandler, Handler
from chirp.config import AppConfig
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
        "_db",
        "_error_handlers",
        "_freeze_lock",
        "_frozen",
        "_kida_env",
        "_middleware",
        "_middleware_list",
        "_migrations_dir",
        "_pending_routes",
        "_pending_tools",
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
        self._frozen: bool = False
        self._freeze_lock: threading.Lock = threading.Lock()

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
    ) -> Callable[[Handler], Handler]:
        """Register a route handler via decorator."""

        def decorator(func: Handler) -> Handler:
            self._check_not_frozen()
            self._pending_routes.append(_PendingRoute(path, func, methods, name))
            return func

        return decorator

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
        """Start the development server via pounce.

        Compiles the app (freezing routes, middleware, templates)
        and starts serving requests with auto-reload enabled.

        Args:
            host: Override bind host.
            port: Override bind port.
            lifecycle_collector: Optional Pounce LifecycleCollector for
                observability.  Forwarded to the Pounce Server.

        """
        self._ensure_frozen()

        _host = host or self.config.host
        _port = port or self.config.port

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
            tool_registry=self._tool_registry,
            mcp_path=self.config.mcp_path,
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
            )
            router.add(route)
        router.compile()
        self._router = router

        # 2. Capture middleware as immutable tuple — append debug
        #    overlays automatically when debug=True so the developer
        #    doesn't have to wire them up manually.
        middleware_list = list(self._middleware_list)
        if self.config.debug:
            from chirp.middleware.inject import HTMLInject
            from chirp.server.htmx_debug import HTMX_DEBUG_SCRIPT

            middleware_list.append(HTMLInject(HTMX_DEBUG_SCRIPT))
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
        no issues (confirms checks ran).
        """
        import sys

        from chirp.contracts import check_hypermedia_surface
        from chirp.server.terminal_checks import format_check_result

        result = check_hypermedia_surface(self)
        sys.stderr.write(format_check_result(result))

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
