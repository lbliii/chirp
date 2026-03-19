"""Server launch orchestration for App."""

import os
import sys
from typing import TYPE_CHECKING

from chirp.config import AppConfig

from .state import MutableAppState

if TYPE_CHECKING:
    from pounce.server import LifecycleCollector

    from chirp.app import App


class ServerLauncher:
    """Runs development or production server based on app config."""

    __slots__ = ("_config", "_mutable")

    def __init__(self, config: AppConfig, mutable_state: MutableAppState) -> None:
        self._config = config
        self._mutable = mutable_state

    def run(
        self,
        app: App,
        *,
        host: str | None,
        port: int | None,
        lifecycle_collector: LifecycleCollector | None,
    ) -> None:
        resolved_host = host or self._config.host
        resolved_port = port or self._config.port
        try:
            self._launch(app, resolved_host, resolved_port, lifecycle_collector)
        except KeyboardInterrupt:
            pass
        except Exception as exc:
            from chirp.server.terminal_errors import format_startup_error

            msg = format_startup_error(exc)
            if msg is not None:
                if os.environ.get("CHIRP_TRACEBACK", "").lower() == "full":
                    raise
                print(msg, file=sys.stderr)
                raise SystemExit(1) from exc
            raise

    def _launch(
        self,
        app: App,
        host: str,
        port: int,
        lifecycle_collector: LifecycleCollector | None,
    ) -> None:
        if self._config.debug:
            from chirp.server.dev import run_dev_server

            reload_dirs = (*self._config.reload_dirs, *self._mutable.reload_dirs_extra)
            run_dev_server(
                app,
                host,
                port,
                reload=self._config.debug,
                reload_include=self._config.reload_include,
                reload_dirs=reload_dirs,
                lifecycle_collector=lifecycle_collector,
            )
            return

        from chirp.server.production import run_production_server

        run_production_server(
            app,
            host=host,
            port=port,
            workers=self._config.workers,
            metrics_enabled=self._config.metrics_enabled,
            metrics_path=self._config.metrics_path,
            rate_limit_enabled=self._config.rate_limit_enabled,
            rate_limit_requests_per_second=self._config.rate_limit_requests_per_second,
            rate_limit_burst=self._config.rate_limit_burst,
            request_queue_enabled=self._config.request_queue_enabled,
            request_queue_max_depth=self._config.request_queue_max_depth,
            sentry_dsn=self._config.sentry_dsn,
            sentry_environment=self._config.sentry_environment,
            sentry_release=self._config.sentry_release,
            sentry_traces_sample_rate=self._config.sentry_traces_sample_rate,
            reload_timeout=self._config.reload_timeout,
            otel_endpoint=self._config.otel_endpoint,
            otel_service_name=self._config.otel_service_name,
            websocket_compression=self._config.websocket_compression,
            websocket_max_message_size=self._config.websocket_max_message_size,
            lifecycle_logging=self._config.lifecycle_logging,
            log_format=self._config.log_format,
            log_level=self._config.log_level,
            worker_mode=self._config.worker_mode,
            max_connections=self._config.max_connections,
            backlog=self._config.backlog,
            keep_alive_timeout=self._config.keep_alive_timeout,
            request_timeout=self._config.request_timeout,
            ssl_certfile=self._config.ssl_certfile,
            ssl_keyfile=self._config.ssl_keyfile,
        )
