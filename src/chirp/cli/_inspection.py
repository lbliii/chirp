"""Shared structured-result boundary for read-only inspection commands."""

from __future__ import annotations

import sys
from typing import Any, Literal


class InspectionResult(dict[str, Any]):
    """JSON-compatible payload with CLI-only presentation metadata.

    The mapping is the complete programmatic and MCP result. The slotted
    attributes are intentionally invisible to JSON serialization and exist
    only so Milo's terminal renderer can preserve Chirp's established text,
    stream, and exit policy.
    """

    __slots__ = ("exit_code", "terminal_stream", "terminal_text")

    def __init__(
        self,
        payload: dict[str, Any],
        *,
        terminal_text: str,
        exit_code: int = 0,
        terminal_stream: Literal["stdout", "stderr"] = "stdout",
    ) -> None:
        super().__init__(payload)
        self.terminal_text = terminal_text
        self.exit_code = exit_code
        self.terminal_stream = terminal_stream


def resolution_error(app_import: str, exc: Exception) -> InspectionResult:
    """Return actionable app-resolution data while preserving CLI behavior."""
    message = str(exc)
    return InspectionResult(
        {
            "ok": False,
            "error": {
                "code": "CHIRP_APP_RESOLUTION",
                "message": message,
                "app_import": app_import,
                "suggestion": "Use module:attribute and ensure it resolves to a Chirp App or factory.",
            },
        },
        terminal_text=f"Error: {message}",
        exit_code=1,
        terminal_stream="stderr",
    )


def inspection_error(
    *,
    code: str,
    message: str,
    suggestion: str,
    context: dict[str, Any] | None = None,
) -> InspectionResult:
    """Return a structured, repairable inspection failure."""
    error = {
        "code": code,
        "message": message,
        "suggestion": suggestion,
    }
    if context:
        error.update(context)
    return InspectionResult(
        {"ok": False, "error": error},
        terminal_text=f"Error: {message}",
        exit_code=1,
        terminal_stream="stderr",
    )


def emit_terminal_result(result: InspectionResult) -> None:
    """Write a result through its legacy terminal channel and exit policy."""
    stream = sys.stderr if result.terminal_stream == "stderr" else sys.stdout
    stream.write(result.terminal_text)
    if result.terminal_text and not result.terminal_text.endswith("\n"):
        stream.write("\n")
    stream.flush()
    if result.exit_code:
        raise SystemExit(result.exit_code)
