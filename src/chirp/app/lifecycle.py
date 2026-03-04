"""ASGI lifespan and worker lifecycle coordination."""

import inspect
from collections.abc import Awaitable, Callable
from typing import Any

from chirp._internal.asgi import Receive, Scope, Send
from chirp.config import AppConfig
from chirp.server.terminal_errors import _plain_error_message
from chirp.tools.events import ToolEventBus

from .state import MutableAppState


async def _run_hook(hook: Callable[..., Any]) -> None:
    result = hook()
    if inspect.isawaitable(result):
        await result


class LifecycleCoordinator:
    """Owns lifespan and worker startup/shutdown behavior."""

    __slots__ = ("_config", "_state", "_ensure_frozen")

    def __init__(
        self,
        config: AppConfig,
        state: MutableAppState,
        ensure_frozen: Callable[[], None],
    ) -> None:
        self._config = config
        self._state = state
        self._ensure_frozen = ensure_frozen

    async def handle_lifespan(self, scope: Scope, receive: Receive, send: Send) -> None:
        del scope
        self._ensure_frozen()
        while True:
            message = await receive()
            msg_type = message["type"]

            if msg_type == "lifespan.startup":
                try:
                    await self._on_startup()
                    await send({"type": "lifespan.startup.complete"})
                except Exception as exc:
                    await send(
                        {"type": "lifespan.startup.failed", "message": _plain_error_message(exc)}
                    )
                    return
            elif msg_type == "lifespan.shutdown":
                await self._on_shutdown()
                await send({"type": "lifespan.shutdown.complete"})
                return

    async def handle_worker_startup(self) -> None:
        for hook in self._state.worker_startup_hooks:
            await _run_hook(hook)

    async def handle_worker_shutdown(self) -> None:
        for hook in self._state.worker_shutdown_hooks:
            await _run_hook(hook)

    async def _on_startup(self) -> None:
        if self._config.audit_sink == "log":
            from chirp.logging import structured_log
            from chirp.security.audit import SecurityEvent, set_security_event_sink

            def _log_sink(event: SecurityEvent) -> None:
                structured_log(
                    20,
                    f"security:{event.name}",
                    path=event.path,
                    method=event.method,
                    user_id=event.user_id,
                    **event.details,
                )

            set_security_event_sink(_log_sink)
        elif self._config.audit_sink == "none":
            from chirp.security.audit import set_security_event_sink

            set_security_event_sink(None)

        if self._state.db is not None:
            await self._state.db.connect()
            from chirp.data.database import _db_var

            _db_var.set(self._state.db)
            if self._state.migrations_dir is not None:
                from chirp.data.migrate import migrate

                await migrate(self._state.db, self._state.migrations_dir)

        for hook in self._state.startup_hooks:
            await _run_hook(hook)

    async def _on_shutdown(self) -> None:
        for hook in self._state.shutdown_hooks:
            await _run_hook(hook)
        if self._state.db is not None:
            await self._state.db.disconnect()
        self._state.tool_events.close()
