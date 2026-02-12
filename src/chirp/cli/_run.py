"""``chirp run`` — development or production server command.

Resolves an import string to a chirp App and starts either the
development server (single worker, auto-reload) or production server
(multi-worker, Phase 5 & 6 features).
"""

import argparse
import sys

from chirp.cli._resolve import resolve_app


def run_server(args: argparse.Namespace) -> None:
    """Start the chirp server (dev or production mode).

    Resolves ``args.app`` to a chirp App, then delegates to either:
    - ``run_dev_server()`` for development (debug=True)
    - ``run_production_server()`` for production (--production flag or debug=False)

    CLI flags override app config for production features.
    """
    try:
        app = resolve_app(args.app)
    except (ModuleNotFoundError, AttributeError, TypeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    host = args.host or app.config.host
    port = args.port or app.config.port

    # Check if production mode requested
    production_mode = args.production or not app.config.debug

    if production_mode:
        # Production mode
        from chirp.server.production import run_production_server

        run_production_server(
            app,
            host=host,
            port=port,
            workers=args.workers if args.workers is not None else app.config.workers,
            # CLI flags override config
            metrics_enabled=args.metrics or app.config.metrics_enabled,
            rate_limit_enabled=args.rate_limit or app.config.rate_limit_enabled,
            request_queue_enabled=args.queue or app.config.request_queue_enabled,
            sentry_dsn=args.sentry_dsn or app.config.sentry_dsn,
            # Use config for other settings
            rate_limit_requests_per_second=app.config.rate_limit_requests_per_second,
            rate_limit_burst=app.config.rate_limit_burst,
            request_queue_max_depth=app.config.request_queue_max_depth,
            sentry_environment=app.config.sentry_environment,
            sentry_release=app.config.sentry_release,
            sentry_traces_sample_rate=app.config.sentry_traces_sample_rate,
            reload_timeout=app.config.reload_timeout,
            otel_endpoint=app.config.otel_endpoint,
            otel_service_name=app.config.otel_service_name,
            websocket_compression=app.config.websocket_compression,
            websocket_max_message_size=app.config.websocket_max_message_size,
            lifecycle_logging=app.config.lifecycle_logging,
            log_format=app.config.log_format,
            log_level=app.config.log_level,
            max_connections=app.config.max_connections,
            backlog=app.config.backlog,
            keep_alive_timeout=app.config.keep_alive_timeout,
            request_timeout=app.config.request_timeout,
            ssl_certfile=app.config.ssl_certfile,
            ssl_keyfile=app.config.ssl_keyfile,
        )
    else:
        # Development mode
        from chirp.server.dev import run_dev_server

        run_dev_server(
            app,
            host,
            port,
            reload=app.config.debug,
            reload_include=app.config.reload_include,
            reload_dirs=app.config.reload_dirs,
            app_path=args.app,
        )
