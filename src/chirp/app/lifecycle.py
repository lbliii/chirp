"""ASGI lifespan and worker lifecycle coordination."""

import contextlib
import inspect
from collections.abc import Callable
from typing import Any

from chirp._internal.asgi import Receive, Scope, Send
from chirp.config import AppConfig
from chirp.server.terminal_errors import _plain_error_message

from .state import MutableAppState


async def _run_hook(hook: Callable[..., Any]) -> None:
    result = hook()
    if inspect.isawaitable(result):
        await result


class LifecycleCoordinator:
    """Owns lifespan and worker startup/shutdown behavior."""

    __slots__ = ("_config", "_ensure_frozen", "_state")

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
        db_connected = False
        try:
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
                db_connected = True
                from chirp.data.database import _db_var

                _db_var.set(self._state.db)
                if self._state.migrations_dir is not None:
                    if self._config.skip_migrations:
                        # Operator opted out of the on-boot run (CHIRP_SKIP_MIGRATIONS
                        # / AppConfig(skip_migrations=True)) so a one-shot deploy job
                        # (`chirp migrate`) can own migration application instead of
                        # every replica racing on startup. Log loudly so a missing
                        # deploy job (= app serving a stale schema) is visible.
                        from chirp.logging import structured_log

                        structured_log(
                            30,  # WARNING
                            "lifecycle:migrations-skipped",
                            migrations_dir=str(self._state.migrations_dir),
                        )
                    else:
                        from chirp.data.migrate import migrate

                        await migrate(self._state.db, self._state.migrations_dir)

            for hook in self._state.startup_hooks:
                await _run_hook(hook)
            # Startup complete: flip the readiness gate True AFTER all startup
            # hooks (and the db connect/migrate) succeed. If startup raised above
            # this point, the except re-raises before we get here, so the flag
            # stays False and /ready keeps returning 503. Single writer,
            # monotonic for a process life (reset only on shutdown).
            self._state.ready = True
        except Exception:
            if db_connected and self._state.db is not None:
                with contextlib.suppress(Exception):
                    await self._state.db.disconnect()
            with contextlib.suppress(Exception):
                self._state.tool_events.close()
            raise

    async def _on_shutdown(self) -> None:
        # Drop out of the load balancer rotation first: /ready returns 503 while
        # shutdown hooks drain.
        self._state.ready = False
        for hook in self._state.shutdown_hooks:
            await _run_hook(hook)
        if self._state.db is not None:
            await self._state.db.disconnect()
        self._state.tool_events.close()
