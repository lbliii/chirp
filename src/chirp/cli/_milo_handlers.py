"""Typed Milo adapters for Chirp-owned CLI handlers.

This module is imported only after Milo selects a command. The functions keep
the public typed contract separate from the existing handler modules while the
handlers continue to own domain behavior and terminal output.
"""

from __future__ import annotations

import traceback
from types import SimpleNamespace
from typing import Annotated, Any

from milo import MinLen, Option, Positional


def _args(**values: object) -> Any:
    return SimpleNamespace(**values)


def new_command(
    name: Annotated[str, Positional("name")],
    minimal: bool = False,
    stream: bool = False,
    sse: bool = False,
    shell: bool = False,
    ai: bool = False,
    with_chirpui: bool = False,
) -> None:
    """Create a new project.

    Args:
        name: Project directory name.
        minimal: Generate a minimal single-file project.
        stream: Include the simulated token-streaming demo.
        sse: Include SSE boilerplate.
        shell: Generate a project with a persistent app shell.
        ai: Scaffold AI chat and its secure supporting stack.
        with_chirpui: Require ChirpUI templates.
    """
    from chirp.cli._new import create_project

    create_project(
        _args(
            name=name,
            minimal=minimal,
            stream=stream,
            sse=sse,
            shell=shell,
            ai=ai,
            with_chirpui=with_chirpui,
        )
    )


def _server_command(
    command: str,
    app: str,
    host: str | None,
    port: int | None,
    production: bool,
    workers: int | None,
    metrics: bool,
    rate_limit: bool,
    queue: bool,
    sentry_dsn: str | None,
) -> None:
    from chirp.cli import _PassthroughError
    from chirp.cli._run import run_server

    try:
        run_server(
            _args(
                command=command,
                app=app,
                host=host,
                port=port,
                production=production,
                workers=workers,
                metrics=metrics,
                rate_limit=rate_limit,
                queue=queue,
                sentry_dsn=sentry_dsn,
                dev_browser_reload=command == "dev",
            )
        )
    except Exception as exc:
        raise _PassthroughError(exc) from exc


def run_command(
    app: Annotated[str, Positional("app")],
    host: str | None = None,
    port: int | None = None,
    production: bool = False,
    workers: int | None = None,
    metrics: bool = False,
    rate_limit: bool = False,
    queue: bool = False,
    sentry_dsn: str | None = None,
) -> None:
    """Start a Chirp server.

    Args:
        app: Application import string, for example myapp:app.
        host: Bind host address.
        port: Bind port number.
        production: Run in production mode.
        workers: Worker count; zero selects automatically.
        metrics: Enable the Prometheus metrics endpoint.
        rate_limit: Enable per-IP rate limiting.
        queue: Enable request queueing.
        sentry_dsn: Sentry DSN for error tracking.
    """
    _server_command(
        "run", app, host, port, production, workers, metrics, rate_limit, queue, sentry_dsn
    )


def dev_command(
    app: Annotated[str, Positional("app")],
    host: str | None = None,
    port: int | None = None,
    production: bool = False,
    workers: int | None = None,
    metrics: bool = False,
    rate_limit: bool = False,
    queue: bool = False,
    sentry_dsn: str | None = None,
) -> None:
    """Start a Chirp development server with browser reload.

    Args:
        app: Application import string, for example myapp:app.
        host: Bind host address.
        port: Bind port number.
        production: Run in production mode.
        workers: Worker count; zero selects automatically.
        metrics: Enable the Prometheus metrics endpoint.
        rate_limit: Enable per-IP rate limiting.
        queue: Enable request queueing.
        sentry_dsn: Sentry DSN for error tracking.
    """
    _server_command(
        "dev", app, host, port, production, workers, metrics, rate_limit, queue, sentry_dsn
    )


def check_command(
    app: Annotated[str, Positional("app")],
    warnings_as_errors: bool = False,
    coverage: bool = False,
    deploy: bool = False,
    json: bool = False,
    baseline: Annotated[str | None, Option(metavar="PATH")] = None,
    include_info: bool = False,
) -> dict[str, Any]:
    """Validate an application's hypermedia contracts.

    Args:
        app: Application import string, for example myapp:app.
        warnings_as_errors: Fail when contract warnings are present.
        coverage: Show route and template coverage counters.
        deploy: Use production-posture severity and strict warnings.
        json: Emit the stable JSON contract report.
        baseline: Compare with a prior JSON baseline at this path.
        include_info: Include informational findings in structured output.
    """
    from chirp.cli._check import collect_check_result

    return collect_check_result(
        app,
        warnings_as_errors=warnings_as_errors,
        coverage=coverage,
        deploy=deploy,
        json_output=json,
        baseline=baseline,
        include_info=include_info,
    )


def diff_command(
    app: Annotated[str, Positional("app")],
    base: Annotated[str, Option(metavar="REF")],
    json: bool = False,
    warnings_as_errors: bool = False,
    deploy: bool = False,
    include_info: bool = False,
) -> dict[str, Any]:
    """Diff an application's hypermedia contracts.

    Args:
        app: Application import string, for example myapp:app.
        base: Git ref to compare against.
        json: Emit a stable JSON diff payload.
        warnings_as_errors: Fail when new warnings appear.
        deploy: Use production-posture severity and strict warnings.
        include_info: Include informational findings in the diff.
    """
    from chirp.cli._diff import collect_diff_result

    return collect_diff_result(
        app,
        base,
        json_output=json,
        warnings_as_errors=warnings_as_errors,
        deploy=deploy,
        include_info=include_info,
    )


def routes_command(app: Annotated[str, Positional("app")]) -> dict[str, Any]:
    """List registered routes.

    Args:
        app: Application import string, for example myapp:app.
    """
    from chirp.cli._routes import collect_routes_result

    return collect_routes_result(app)


def security_check_command(app: Annotated[str, Positional("app")]) -> None:
    """Audit an application's security configuration.

    Args:
        app: Application import string, for example myapp:app.
    """
    from chirp.cli._security_check import run_security_check

    try:
        run_security_check(_args(app=app))
    except ModuleNotFoundError, AttributeError, TypeError:
        traceback.print_exc()
        raise SystemExit(1) from None


def freeze_command(
    app: Annotated[str, Positional("app")],
    output: Annotated[str, Positional("output")],
    exclude: Annotated[list[str] | None, Option(metavar="EXCLUDE"), MinLen(1)] = None,
) -> None:
    """Render routes to static HTML files.

    Args:
        app: Application import string, for example myapp:app.
        output: Output directory for frozen HTML files.
        exclude: One or more URL prefixes to exclude.
    """
    from chirp.cli._freeze import run_freeze

    run_freeze(_args(app=app, output=output, exclude=exclude))


def makemigrations_command(
    db: Annotated[str, Option(metavar="DB")],
    schema: Annotated[str, Option(metavar="SCHEMA")],
    migrations_dir: Annotated[str, Option(metavar="MIGRATIONS_DIR")] = "migrations",
) -> None:
    """Generate a schema migration from a SQL diff.

    Args:
        db: Database URL.
        schema: SQL schema file or Python module containing SCHEMA.
        migrations_dir: Output directory for migration files.
    """
    from chirp.cli._makemigrations import run_makemigrations

    run_makemigrations(_args(db=db, schema=schema, migrations_dir=migrations_dir))


def migrate_command(
    db: Annotated[str, Option(metavar="DB")],
    migrations_dir: Annotated[str, Option(metavar="MIGRATIONS_DIR")] = "migrations",
) -> None:
    """Apply pending schema migrations.

    Args:
        db: Database URL.
        migrations_dir: Directory containing migration files.
    """
    from chirp.cli._migrate import run_migrate

    run_migrate(_args(db=db, migrations_dir=migrations_dir))


def shapes_codegen_command(
    path: Annotated[str, Positional("path")] = ".",
    dry_run: bool = False,
    audit: bool = False,
    migrations: Annotated[str, Option(metavar="MIGRATIONS_DIR")] = "migrations",
) -> None:
    """Suggest @shape decorators and audit Shape drift.

    Args:
        path: File or directory to scan; with --audit, an app import string.
        dry_run: Print suggestions without writing files.
        audit: Audit surface contracts for missing Shapes.
        migrations: Reserved migration directory for future incremental output.
    """
    from chirp.cli._shapes_codegen import run_shapes_codegen

    run_shapes_codegen(_args(path=path, dry_run=dry_run, audit=audit, migrations_dir=migrations))
