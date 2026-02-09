"""Terminal error formatting for chirp development server.

Provides structured, human-readable error output for the terminal during
``chirp run``. Replaces raw ``logger.exception()`` with clean diagnostics
that highlight the useful information.

For Kida template errors:
    Calls ``exc.format_compact()`` and adds Chirp-specific context (route,
    method, path). Produces output like::

        -- Template Error -----------------------------------------------
        K-RUN-001: Undefined variable 'usernme' in base.html:42

           |
        >42 | <h1>{{ usernme }}</h1>
           |

        Route:  GET /dashboard
        Hint:   Use {{ usernme | default('') }} for optional variables
        Docs:   https://kida.dev/docs/errors/#k-run-001
        -----------------------------------------------------------------

For non-template errors:
    Uses configurable traceback verbosity (compact/full/minimal) controlled
    by the ``CHIRP_TRACEBACK`` environment variable.
"""

from __future__ import annotations

import logging
import os
import traceback as _traceback
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chirp.http.request import Request

logger = logging.getLogger("chirp.server")

# Width of the terminal error banner
_BANNER_WIDTH = 65


def _is_kida_error(exc: BaseException) -> bool:
    """Check if an exception originates from the kida template engine."""
    module = type(exc).__module__ or ""
    return "kida" in module


def _is_app_frame(filename: str) -> bool:
    """True if the frame is from the application (not stdlib/site-packages)."""
    if "site-packages" in filename:
        return False
    if filename.startswith("<"):
        return False
    import os as _os

    stdlib_prefix = _os.path.dirname(_os.__file__)
    return not filename.startswith(stdlib_prefix)


def format_template_error(exc: BaseException, request: Request) -> str:
    """Format a Kida template error for terminal display.

    Uses ``exc.format_compact()`` and wraps it with a banner and
    request context.

    Args:
        exc: A Kida template exception (TemplateError subclass).
        request: The request that triggered the error.

    Returns:
        Formatted multi-line string for terminal output.
    """
    parts: list[str] = []

    # Banner
    parts.append(f"-- Template Error {'-' * (_BANNER_WIDTH - 18)}")

    # Compact error from Kida
    if hasattr(exc, "format_compact"):
        parts.append(exc.format_compact())
    else:
        parts.append(str(exc))

    # Request context
    parts.append("")
    parts.append(f"  Route: {request.method} {request.path}")

    # Close banner
    parts.append("-" * _BANNER_WIDTH)

    return "\n".join(parts)


def format_compact_traceback(exc: BaseException) -> str:
    """Format a non-template error with compact traceback.

    Shows only application frames + error summary, suppressing
    framework internals from kida, starlette, uvicorn, anyio.

    Args:
        exc: Any exception.

    Returns:
        Formatted multi-line string for terminal output.
    """
    parts: list[str] = []

    # Extract frames
    tb = exc.__traceback__
    frames = _traceback.extract_tb(tb) if tb else []

    # Filter to app frames
    app_frames = [f for f in frames if _is_app_frame(f.filename)]

    # If no app frames, show last 3 frames instead
    display_frames = app_frames if app_frames else frames[-3:]

    parts.append(f"{type(exc).__name__}: {exc}")

    if display_frames:
        parts.append("  Trace (app frames):")
        for frame in display_frames[-5:]:  # Show at most 5 app frames
            parts.append(f"    {frame.filename}:{frame.lineno} in {frame.name}")
            if frame.line:
                parts.append(f"      {frame.line.strip()}")

    return "\n".join(parts)


def format_minimal_error(exc: BaseException) -> str:
    """One-line error summary for minimal verbosity.

    Args:
        exc: Any exception.

    Returns:
        Single-line error string.
    """
    tb = exc.__traceback__
    frames = _traceback.extract_tb(tb) if tb else []
    last = frames[-1] if frames else None
    location = f" at {last.filename}:{last.lineno}" if last else ""
    return f"{type(exc).__name__}{location}: {exc}"


def log_error(exc: BaseException, request: Request) -> None:
    """Log an internal error with appropriate formatting.

    Detects Kida template errors and formats them cleanly. For non-template
    errors, uses the traceback verbosity level from ``CHIRP_TRACEBACK``
    (compact, full, minimal). Defaults to compact.

    This replaces the raw ``logger.exception()`` call in
    ``handle_internal_error()``.

    Args:
        exc: The exception that caused the 500 error.
        request: The request that triggered the error.
    """
    if _is_kida_error(exc):
        # Template errors get the clean format
        logger.error(
            "500 %s %s\n%s",
            request.method,
            request.path,
            format_template_error(exc, request),
        )
        return

    # Non-template errors: check verbosity
    traceback_style = os.environ.get("CHIRP_TRACEBACK", "compact").lower()

    if traceback_style == "full":
        # Full Python traceback (original behavior)
        logger.exception("500 %s %s", request.method, request.path)
    elif traceback_style == "minimal":
        logger.error(
            "500 %s %s — %s",
            request.method,
            request.path,
            format_minimal_error(exc),
        )
    else:
        # Default: compact (app frames only)
        logger.error(
            "500 %s %s\n%s",
            request.method,
            request.path,
            format_compact_traceback(exc),
        )
