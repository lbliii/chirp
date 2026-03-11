"""ASGI runtime dispatch for App."""

from collections.abc import Callable

from chirp._internal.asgi import Receive, Scope, Send
from chirp.config import AppConfig
from chirp.server.handler import create_request_handler, handle_request

from .lifecycle import LifecycleCoordinator
from .state import MutableAppState, RuntimeAppState


class ASGIRuntime:
    """Dispatches ASGI scopes to lifecycle or request handling."""

    __slots__ = ("_compiled_handler", "_config", "_ensure_frozen", "_lifecycle", "_mutable", "_runtime")

    def __init__(
        self,
        config: AppConfig,
        mutable_state: MutableAppState,
        runtime_state: RuntimeAppState,
        lifecycle: LifecycleCoordinator,
        ensure_frozen: Callable[[], None],
    ) -> None:
        self._config = config
        self._mutable = mutable_state
        self._runtime = runtime_state
        self._lifecycle = lifecycle
        self._ensure_frozen = ensure_frozen
        self._compiled_handler = None

    def _get_compiled_handler(self):
        if self._compiled_handler is None:
            self._compiled_handler = create_request_handler(
                router=self._runtime.router,
                middleware=self._runtime.middleware,
                tool_registry=self._runtime.tool_registry,
                mcp_path=self._config.mcp_path,
                debug=self._config.debug,
                providers=self._mutable.providers or None,
                kida_env=self._runtime.kida_env,
                oob_registry=self._runtime.oob_registry,
                fragment_target_registry=self._runtime.fragment_target_registry,
            )
        return self._compiled_handler

    async def handle(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "lifespan":
            await self._lifecycle.handle_lifespan(scope, receive, send)
            return
        if scope["type"] == "pounce.worker.startup":
            await self._lifecycle.handle_worker_startup()
            return
        if scope["type"] == "pounce.worker.shutdown":
            await self._lifecycle.handle_worker_shutdown()
            return

        self._ensure_frozen()
        assert self._runtime.router is not None

        await handle_request(
            scope,
            receive,
            send,
            router=self._runtime.router,
            middleware=self._runtime.middleware,
            error_handlers=self._mutable.error_handlers,
            kida_env=self._runtime.kida_env,
            debug=self._config.debug,
            providers=self._mutable.providers or None,
            tool_registry=self._runtime.tool_registry,
            mcp_path=self._config.mcp_path,
            sse_heartbeat_interval=self._config.sse_heartbeat_interval,
            sse_retry_ms=self._config.sse_retry_ms,
            sse_close_event=self._config.sse_close_event,
            compiled_handler=self._get_compiled_handler(),
            oob_registry=self._runtime.oob_registry,
            fragment_target_registry=self._runtime.fragment_target_registry,
        )
