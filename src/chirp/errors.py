"""Chirp exception hierarchy.

Shared across Router, App, handler, and middleware so every module
raises and catches the same types.
"""

from dataclasses import dataclass


class ChirpError(Exception):
    """Base for all chirp-specific errors."""


class ConfigurationError(ChirpError):
    """Raised when app configuration is invalid.

    Typically caught during ``App._freeze()`` at startup.
    """


class BlockNotFoundError(ChirpError, KeyError):
    """A named template block does not exist in the target template.

    Raised at render time when a region update (OOB fragment, Suspense
    deferred block, layout contract entry) references a block the
    template does not define. App-level ``register_oob_region(..., optional=True)``
    is the opt-out for shell regions that may legitimately be absent
    from some layouts; non-optional misses reach here and propagate
    so they're visible rather than silently producing empty swaps.

    Multi-inherits from ``KeyError`` so existing ``except KeyError`` handlers
    (including Kida's documented ``render_block`` contract) still catch it.
    """

    def __init__(self, *, template: str, block: str, region: str | None = None) -> None:
        self.template = template
        self.block = block
        self.region = region
        location = f" (OOB region {region!r})" if region else ""
        message = (
            f"Block {block!r} not found in template {template!r}{location}. "
            "Either add the block to the layout template, or if this region is "
            "legitimately optional, register it with optional=True."
        )
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class HTTPError(ChirpError):
    """An error that maps directly to an HTTP status code.

    Raised by the router, middleware, or handlers. The ASGI handler
    catches these and dispatches to the matching ``@app.error()`` handler.
    """

    status: int
    detail: str = ""
    headers: tuple[tuple[str, str], ...] = ()

    def __str__(self) -> str:
        if self.detail:
            return f"{self.status}: {self.detail}"
        return str(self.status)


class NotFound(HTTPError):  # noqa: N818 — conventional name in web frameworks
    """404 — no route matched the request path."""

    def __init__(self, detail: str = "Not Found") -> None:
        super().__init__(status=404, detail=detail)


class MethodNotAllowed(HTTPError):  # noqa: N818 — conventional name in web frameworks
    """405 — route exists but not for this HTTP method.

    Includes an ``Allow`` header listing the valid methods and embeds
    the allowed methods in the detail string for developer visibility.
    """

    def __init__(self, allowed: frozenset[str], detail: str = "") -> None:
        allow_value = ", ".join(sorted(allowed))
        default_detail = f"Method not allowed. Allowed methods: {allow_value}"
        super().__init__(
            status=405,
            detail=detail or default_detail,
            headers=(("Allow", allow_value),),
        )


class PayloadTooLarge(HTTPError):  # noqa: N818 — conventional name in web frameworks
    """413 — request body or multipart upload exceeds a configured limit.

    Raised at the byte boundary (``Request.body``/``Request.stream``) when a
    body of any content type exceeds the general ``AppConfig.max_request_body_size``
    cap, and by the multipart parser when a submission exceeds the multipart-
    specific ``AppConfig.max_upload_size`` (total part bytes) or
    ``AppConfig.max_upload_parts`` (part count). Surfacing this before the whole
    body is joined into RAM is what keeps a multi-GB upload or a multipart bomb
    from OOMing the worker.
    """

    def __init__(self, detail: str = "Payload Too Large") -> None:
        super().__init__(status=413, detail=detail)


class ToolAuthError(ChirpError):
    """Auth denial raised from a tool handler (401/403).

    Mutable counterpart to :class:`HTTPError` for the MCP tool path:
    frozen ``HTTPError`` cannot accept ``__traceback__`` assignment inside
    ``trace_span`` / ``contextlib``, so skill (and similar) gates catch the
    shared ``enforce_auth`` ``HTTPError`` and re-raise this type. MCP
    ``tools/call`` maps it to a JSON-RPC error.
    """

    def __init__(self, *, status: int = 403, detail: str = "Forbidden") -> None:
        self.status = status
        self.detail = detail
        super().__init__(detail)
