"""Chirp application class.

Mutable during setup (route registration, middleware, filters).
Frozen at runtime when app.run() or __call__() is first invoked.
"""

import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from kida import Environment

from chirp._internal.asgi import Receive, Scope, Send
from chirp._internal.types import ErrorHandler, Handler
from chirp.config import AppConfig
from chirp.middleware.protocol import Middleware
from chirp.routing.route import Route
from chirp.routing.router import Router
from chirp.server.handler import handle_request
from chirp.templating.integration import create_environment


@dataclass(slots=True)
class _PendingRoute:
    """A route waiting to be compiled."""

    path: str
    handler: Handler
    methods: list[str] | None
    name: str | None


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
        "_error_handlers",
        "_freeze_lock",
        "_frozen",
        "_kida_env",
        "_middleware",
        "_middleware_list",
        "_pending_routes",
        # Compiled state (populated by _freeze)
        "_router",
        "_template_filters",
        "_template_globals",
        "config",
    )

    def __init__(self, config: AppConfig | None = None) -> None:
        self.config: AppConfig = config or AppConfig()
        self._pending_routes: list[_PendingRoute] = []
        self._middleware_list: list[Middleware] = []
        self._error_handlers: dict[int | type, ErrorHandler] = {}
        self._template_filters: dict[str, Callable[..., Any]] = {}
        self._template_globals: dict[str, Any] = {}
        self._frozen: bool = False
        self._freeze_lock: threading.Lock = threading.Lock()

        # Compiled state — set during _freeze()
        self._router: Router | None = None
        self._middleware: tuple[Callable[..., Any], ...] = ()
        self._kida_env: Environment | None = None

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

    # -- Lifecycle --

    def run(
        self,
        host: str | None = None,
        port: int | None = None,
    ) -> None:
        """Start the development server via pounce.

        Compiles the app (freezing routes, middleware, templates)
        and starts serving requests with auto-reload enabled.
        """
        self._ensure_frozen()

        _host = host or self.config.host
        _port = port or self.config.port

        from chirp.server.dev import run_dev_server

        run_dev_server(self, _host, _port, reload=self.config.debug)

    # -- ASGI interface --

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ASGI 3.0 entry point."""
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
        )

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

        # 2. Capture middleware as immutable tuple
        self._middleware = tuple(self._middleware_list)

        # 3. Initialize kida environment
        self._kida_env = create_environment(
            self.config,
            self._template_filters,
            self._template_globals,
        )

        self._frozen = True

    def _check_not_frozen(self) -> None:
        if self._frozen:
            msg = (
                "Cannot modify the app after it has started serving requests. "
                "Register routes, middleware, and filters before calling app.run()."
            )
            raise RuntimeError(msg)
