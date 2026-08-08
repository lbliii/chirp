"""Chirp CLI registration backed by Milo's public lazy-command APIs.

The packaged entry point remains ``chirp.cli:main``. Command implementations
stay in their existing modules; this module owns typed metadata and lazy import
paths without importing a handler to render help or report a parse error.
"""

from __future__ import annotations

import sys
from typing import Any

from milo import CLI

_CLI_ONLY = ("cli",)
_INSPECTION_SURFACES = ("cli", "mcp", "llms")
_MISSING = object()


class _PassthroughError(BaseException):
    """Carry a Chirp-owned exception past Milo's terminal normalization."""

    def __init__(self, original: Exception) -> None:
        super().__init__(str(original))
        self.original = original


def _property(
    value_type: str,
    description: str,
    *,
    default: Any = _MISSING,
    presentation: dict[str, Any] | None = None,
    items: dict[str, Any] | None = None,
    min_items: int | None = None,
) -> dict[str, Any]:
    prop: dict[str, Any] = {"type": value_type, "description": description}
    if presentation is not None:
        prop["x-milo-cli"] = presentation
    if items is not None:
        prop["items"] = items
    if min_items is not None:
        prop["minItems"] = min_items
    if default is not _MISSING:
        prop["default"] = default
    return prop


def _positional(value_type: str, description: str, name: str, *, default: Any = _MISSING):
    return _property(
        value_type,
        description,
        default=default,
        presentation={"kind": "positional", "metavar": name},
    )


def _option(value_type: str, description: str, metavar: str, *, default: Any = _MISSING):
    return _property(
        value_type,
        description,
        default=default,
        presentation={"kind": "option", "metavar": metavar},
    )


def _flag(description: str) -> dict[str, Any]:
    return _property("boolean", description, default=False)


def _schema(
    properties: dict[str, dict[str, Any]],
    *required: str,
) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = list(required)
    return schema


def _server_schema() -> dict[str, Any]:
    return _schema(
        {
            "app": _positional(
                "string", "Application import string, for example myapp:app.", "app"
            ),
            "host": _property("string", "Bind host address.", default=None),
            "port": _property("integer", "Bind port number.", default=None),
            "production": _flag("Run in production mode."),
            "workers": _property(
                "integer", "Worker count; zero selects automatically.", default=None
            ),
            "metrics": _flag("Enable the Prometheus metrics endpoint."),
            "rate_limit": _flag("Enable per-IP rate limiting."),
            "queue": _flag("Enable request queueing."),
            "sentry_dsn": _property("string", "Sentry DSN for error tracking.", default=None),
        },
        "app",
    )


def _schemas() -> dict[str, dict[str, Any]]:
    """Build fresh precomputed schemas for one invocation-local registry."""
    return {
        "new": _schema(
            {
                "name": _positional("string", "Project directory name.", "name"),
                "minimal": _flag("Generate a minimal single-file project."),
                "stream": _flag("Include the simulated token-streaming demo."),
                "sse": _flag("Include SSE boilerplate."),
                "shell": _flag("Generate a project with a persistent app shell."),
                "ai": _flag("Scaffold AI chat and its secure supporting stack."),
                "with_chirpui": _flag("Require ChirpUI templates."),
            },
            "name",
        ),
        "run": _server_schema(),
        "dev": _server_schema(),
        "check": _schema(
            {
                "app": _positional(
                    "string", "Application import string, for example myapp:app.", "app"
                ),
                "warnings_as_errors": _flag("Fail when contract warnings are present."),
                "coverage": _flag("Show route and template coverage counters."),
                "deploy": _flag("Use production-posture severity and strict warnings."),
                "json": _flag("Emit the stable JSON contract report."),
                "baseline": _option(
                    "string",
                    "Compare with a prior JSON baseline at this path.",
                    "PATH",
                    default=None,
                ),
                "include_info": _flag("Include informational findings in structured output."),
            },
            "app",
        ),
        "diff": _schema(
            {
                "app": _positional(
                    "string", "Application import string, for example myapp:app.", "app"
                ),
                "base": _option("string", "Git ref to compare against.", "REF"),
                "json": _flag("Emit a stable JSON diff payload."),
                "warnings_as_errors": _flag("Fail when new warnings appear."),
                "deploy": _flag("Use production-posture severity and strict warnings."),
                "include_info": _flag("Include informational findings in the diff."),
            },
            "app",
            "base",
        ),
        "routes": _schema(
            {
                "app": _positional(
                    "string", "Application import string, for example myapp:app.", "app"
                )
            },
            "app",
        ),
        "security-check": _schema(
            {
                "app": _positional(
                    "string", "Application import string, for example myapp:app.", "app"
                )
            },
            "app",
        ),
        "freeze": _schema(
            {
                "app": _positional(
                    "string", "Application import string, for example myapp:app.", "app"
                ),
                "output": _positional(
                    "string", "Output directory for frozen HTML files.", "output"
                ),
                "exclude": _property(
                    "array",
                    "One or more URL prefixes to exclude.",
                    default=None,
                    presentation={"kind": "option", "metavar": "EXCLUDE"},
                    items={"type": "string"},
                    min_items=1,
                ),
            },
            "app",
            "output",
        ),
        "makemigrations": _schema(
            {
                "db": _option("string", "Database URL.", "DB"),
                "schema": _option(
                    "string", "SQL schema file or Python module containing SCHEMA.", "SCHEMA"
                ),
                "migrations_dir": _option(
                    "string",
                    "Output directory for migration files.",
                    "MIGRATIONS_DIR",
                    default="migrations",
                ),
            },
            "db",
            "schema",
        ),
        "migrate": _schema(
            {
                "db": _option("string", "Database URL.", "DB"),
                "migrations_dir": _option(
                    "string",
                    "Directory containing migration files.",
                    "MIGRATIONS_DIR",
                    default="migrations",
                ),
            },
            "db",
        ),
        "shapes-codegen": _schema(
            {
                "path": _positional(
                    "string",
                    "File or directory to scan; with --audit, an app import string.",
                    "path",
                    default=".",
                ),
                "dry_run": _flag("Print suggestions without writing files."),
                "audit": _flag("Audit surface contracts for missing Shapes."),
                "migrations": _option(
                    "string",
                    "Reserved migration directory for future incremental output.",
                    "MIGRATIONS_DIR",
                    default="migrations",
                ),
            }
        ),
        "skill.publish": _schema(
            {
                "app": _positional(
                    "string", "Application import string, for example myapp:app.", "app"
                ),
                "corpus": _option(
                    "string",
                    "JSON path to a golden NL smoke corpus (array of CorpusPrompt).",
                    "PATH",
                    default=None,
                ),
                "fixture": _flag("Use the built-in fixture-echo corpus from chirp.skill.smoke."),
                "warnings_as_errors": _flag("Fail the check stage when contract warnings exist."),
                "json": _flag("Emit the stable JSON publish receipt."),
            },
            "app",
        ),
    }


def _version_report() -> str:
    from chirp.cli._version import version_report

    return version_report()


def _render_inspection_result(result: Any, _ctx: Any) -> str:
    """Render structured inspection data only at the human CLI boundary."""
    from chirp.cli._inspection import InspectionResult, emit_terminal_result

    if not isinstance(result, InspectionResult):
        return str(result)
    if result.exit_code:
        emit_terminal_result(result)
    return result.terminal_text


def _build_cli() -> CLI:
    """Build one registry per invocation to isolate Milo's parser state."""
    cli = CLI(
        name="chirp",
        description="Chirp — A Python web framework for the modern web platform.",
        version_flags=("-V", "--version"),
        version_report=_version_report,
    )
    schemas = _schemas()

    def register(
        name: str,
        description: str,
        *,
        annotations: dict[str, Any] | None = None,
        surfaces: tuple[str, ...] = _CLI_ONLY,
        structured: bool = False,
    ) -> None:
        cli.lazy_command(
            name,
            f"chirp.cli._milo_handlers:{name.replace('-', '_')}_command",
            description=description,
            schema=schemas[name],
            surfaces=surfaces,
            display_result=structured,
            terminal_renderer=_render_inspection_result if structured else None,
            annotations=annotations,
        )

    register(
        "new",
        "Create a new project",
        annotations={"destructiveHint": True, "openWorldHint": True},
    )
    register("run", "Start dev or production server", annotations={"openWorldHint": True})
    register(
        "dev",
        "Development server with browser reload on template/CSS changes",
        annotations={"openWorldHint": True},
    )
    inspection_annotations = {"readOnlyHint": True, "openWorldHint": True}
    register(
        "check",
        "Validate hypermedia contracts",
        annotations=inspection_annotations,
        surfaces=_INSPECTION_SURFACES,
        structured=True,
    )
    register(
        "diff",
        "Diff hypermedia contracts against a git base ref",
        annotations=inspection_annotations,
        surfaces=_INSPECTION_SURFACES,
        structured=True,
    )
    register(
        "routes",
        "List registered routes",
        annotations=inspection_annotations,
        surfaces=_INSPECTION_SURFACES,
        structured=True,
    )
    register("security-check", "Audit app config against OWASP security checklist")
    register(
        "freeze",
        "Render routes to static HTML files",
        annotations={"destructiveHint": True, "openWorldHint": True},
    )
    register(
        "makemigrations",
        "Auto-generate schema migration from SQL diff",
        annotations={"destructiveHint": True, "openWorldHint": True},
    )
    register(
        "migrate",
        "Apply pending schema migrations (one-shot deploy job)",
        annotations={
            "destructiveHint": True,
            "idempotentHint": True,
            "openWorldHint": True,
        },
    )
    register("shapes-codegen", "Suggest @shape decorators and audit Shape drift")

    skill = cli.group("skill", description="Skill authoring and publish-oracle gates")
    skill.lazy_command(
        "publish",
        "chirp.cli._milo_handlers:skill_publish_command",
        description="Run check + freeze + smoke and emit a publish receipt",
        schema=schemas["skill.publish"],
        surfaces=_CLI_ONLY,
        display_result=True,
        terminal_renderer=_render_inspection_result,
        annotations={"readOnlyHint": True, "openWorldHint": True},
    )
    return cli


def main(argv: list[str] | None = None) -> None:
    """Run the packaged ``chirp`` command through an invocation-local Milo CLI."""
    resolved_argv = list(sys.argv[1:] if argv is None else argv)
    try:
        _build_cli().run(resolved_argv)
    except _PassthroughError as exc:
        raise exc.original.with_traceback(exc.original.__traceback__) from None
    if not resolved_argv:
        raise SystemExit(0)
