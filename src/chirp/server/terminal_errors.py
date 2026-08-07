"""Terminal error formatting for chirp development server.

Provides structured, human-readable error output for the terminal during
``chirp run``. Replaces raw ``logger.exception()`` with clean diagnostics
that highlight the useful information.

For startup errors:
    Maps known startup exceptions (port conflicts, TLS misconfiguration,
    lifespan failures, config validation) to clean, actionable messages
    via ``format_startup_error()``.  Returns ``None`` for unrecognised
    errors so the caller can fall back to the default traceback.

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

import errno
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


def _plain_error_message(exc: BaseException) -> str:
    """Error message safe for HTTP/SSE/JSON (no ANSI codes)."""
    fmt = getattr(exc, "format_compact", None)
    msg = fmt() if fmt is not None else str(exc)
    if _is_kida_error(exc):
        from kida.environment.terminal import strip_colors

        return strip_colors(msg)
    return msg


def _html_error_message(exc: BaseException, *, structured_panel: bool = False) -> str:
    """Error message safe for HTML display (no ANSI escape codes).

    When *structured_panel* is True, the debug page renders source snippets,
    stacks, and hints separately — so return a one-line summary instead of
    ``format_compact()``'s full terminal-style block.
    """
    if not _is_kida_error(exc):
        return str(exc)

    to_diag = getattr(exc, "to_diagnostic", None)
    if structured_panel and to_diag is not None:
        return to_diag().message

    plain = _plain_error_message(exc)
    if structured_panel and plain:
        return plain.splitlines()[0]
    return plain


def _is_app_frame(filename: str) -> bool:
    """True if the frame is from the application (not stdlib/site-packages)."""
    if "site-packages" in filename:
        return False
    if filename.startswith("<"):
        return False
    import os as _os

    stdlib_prefix = _os.path.dirname(_os.__file__)
    return not filename.startswith(stdlib_prefix)


def format_template_error(exc: BaseException, request: Request | None = None) -> str:
    """Format a Kida template error for logging (plain text, no ANSI).

    Uses the same compact body as :func:`_plain_error_message` — Kida's
    ``format_compact()`` with ANSI stripped so JSON/structured logs stay readable.

    Args:
        exc: A Kida template exception (TemplateError subclass).
        request: The request that triggered the error (optional).

    Returns:
        Formatted multi-line string for log output.
    """
    parts: list[str] = []

    # Banner
    parts.append(f"-- Template Error {'-' * (_BANNER_WIDTH - 18)}")

    # Compact error from Kida (no ANSI; matches HTTP/SSE error bodies)
    parts.append(_plain_error_message(exc))

    # Request context (when available)
    if request is not None:
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


#: errno values that mean "the client went away mid-response" on a bare OSError.
_CLIENT_DISCONNECT_ERRNOS = frozenset({errno.ECONNRESET, errno.EPIPE, errno.ECONNABORTED})


def is_client_disconnect(exc: BaseException) -> bool:
    """True when *exc* signals the client closed the connection mid-response.

    Long-lived streaming/SSE responses routinely end with the peer vanishing — a
    browser tab closes, a proxy times the idle connection out — which surfaces in
    the server's send/drain path as a TCP reset or broken pipe. These are not
    server faults: there is nothing left to send and nothing to alert on. Callers
    log them at ``DEBUG`` and skip the 500 error path (see
    :func:`chirp.realtime.sse.handle_sse` and
    :func:`chirp.server.sender.send_streaming_response`).

    Covers the peer-gone classes (``ConnectionResetError`` / ``BrokenPipeError`` /
    ``ConnectionAbortedError``) plus a bare :class:`OSError` carrying a disconnect
    ``errno`` (``ECONNRESET`` / ``EPIPE`` / ``ECONNABORTED``).

    Deliberately narrower than ``ConnectionError``: the broad ``except`` blocks
    that call this also wrap the *user's* stream generator body, so a generic
    ``ConnectionError`` — most notably ``ConnectionRefusedError`` (``ECONNREFUSED``,
    an *outbound* failure when the generator's own upstream DB/cache/HTTP target
    refuses) — is a genuine server error that must stay loud, not be swallowed as
    a benign client disconnect.
    """
    if isinstance(exc, ConnectionResetError | BrokenPipeError | ConnectionAbortedError):
        return True
    return isinstance(exc, OSError) and exc.errno in _CLIENT_DISCONNECT_ERRNOS


def log_error(exc: BaseException, request: Request | None = None) -> None:
    """Log an internal error with appropriate formatting.

    Detects Kida template errors and formats them cleanly. For non-template
    errors, uses the traceback verbosity level from ``CHIRP_TRACEBACK``
    (compact, full, minimal). Defaults to compact.

    This replaces the raw ``logger.exception()`` call in
    ``handle_internal_error()``.

    Args:
        exc: The exception that caused the 500 error.
        request: The request that triggered the error (optional for
            streaming/SSE contexts where a request may not be available).
    """
    # Build a prefix for log messages
    prefix = f"500 {request.method} {request.path}" if request is not None else "Server error"

    if _is_kida_error(exc):
        # Template errors get the clean format
        logger.error(
            "%s\n%s",
            prefix,
            format_template_error(exc, request),
        )
        return

    # Non-template errors: check verbosity
    traceback_style = os.environ.get("CHIRP_TRACEBACK", "compact").lower()

    if traceback_style == "full":
        # Full Python traceback (original behavior)
        logger.exception(prefix)  # noqa: LOG004, RUF100 -- caller's exception context is active
    elif traceback_style == "minimal":
        logger.error(
            "%s — %s",
            prefix,
            format_minimal_error(exc),
        )
    else:
        # Default: compact (app frames only)
        logger.error(
            "%s\n%s",
            prefix,
            format_compact_traceback(exc),
        )


def format_startup_error(exc: BaseException, *, cli: bool = False) -> str | None:
    """Map a startup exception to a clean, actionable terminal message.

    Args:
        exc: The exception raised during startup.
        cli: When ``True``, hints reference ``chirp run --port`` instead of
            ``app.run(port=...)``.

    Returns ``None`` if the exception is not a recognised startup error
    (caller should re-raise or fall back to default handling).
    """
    from pounce import PounceError

    from chirp.errors import ConfigurationError

    # OSError from socket binding (port in use, permission denied).
    # Check PounceError first — some subclasses may also inherit OSError.
    if isinstance(exc, OSError) and not isinstance(exc, PounceError):
        if exc.errno == errno.EADDRINUSE or "already in use" in str(exc).lower():
            hint = "    chirp run myapp:app --port 8001" if cli else "    app.run(port=8001)"
            return f"Error: {exc}\n\n  Kill the other process or use a different port:\n{hint}"
        if exc.errno == errno.EACCES:
            return f"Error: {exc}\n\n  Try a port above 1024, or run with elevated privileges."
        return f"Error: {exc}"

    # Pounce structured errors (LifespanError, TLSError, SupervisorError, …)
    if isinstance(exc, PounceError):
        return _with_cause(f"Error: {exc}", exc)

    # Chirp configuration errors
    if isinstance(exc, ConfigurationError):
        return f"Configuration error: {exc}"

    # Generic ValueError from config validation
    if isinstance(exc, ValueError):
        return f"Configuration error: {exc}"

    return None


def _with_cause(msg: str, exc: BaseException) -> str:
    """Append ``__cause__`` context when present (e.g. LifespanError wrapping a DB error)."""
    cause = exc.__cause__
    if cause is not None:
        return f"{msg}\n  Caused by: {type(cause).__name__}: {cause}"
    return msg
