"""Static file serving middleware.

Serves files from a directory for matching URL prefixes.
Falls through to the next handler for non-matching paths.
"""

import mimetypes
from pathlib import Path

from chirp.http.request import Request
from chirp.http.response import Response
from chirp.middleware.protocol import Next


class StaticFiles:
    """Middleware that serves static files from a directory.

    Files are served for paths matching the configured prefix.
    Non-matching paths fall through to the next handler.

    Security: resolves symlinks and verifies the final path
    is within the configured directory to prevent path traversal.

    Usage::

        app.add_middleware(StaticFiles(
            directory="./static",
            prefix="/static",
        ))
    """

    __slots__ = ("_directory", "_prefix")

    def __init__(self, directory: str | Path, prefix: str = "/static") -> None:
        self._directory = Path(directory).resolve()
        # Normalize prefix: ensure leading slash, strip trailing
        self._prefix = "/" + prefix.strip("/")

    async def __call__(self, request: Request, next: Next) -> Response:
        """Serve a static file or fall through."""
        # Only serve GET and HEAD
        if request.method not in ("GET", "HEAD"):
            return await next(request)

        # Check if path matches prefix
        if not request.path.startswith(self._prefix + "/") and request.path != self._prefix:
            return await next(request)

        # Extract relative file path
        relative = request.path[len(self._prefix) :].lstrip("/")
        if not relative:
            return await next(request)

        # Resolve the file path and check for traversal
        file_path = (self._directory / relative).resolve()
        if not file_path.is_relative_to(self._directory):
            # Path traversal attempt
            return Response(body="Forbidden", status=403)

        # Check if file exists and is a regular file
        if not file_path.is_file():
            return await next(request)

        # Determine content type
        content_type, _ = mimetypes.guess_type(str(file_path))
        if content_type is None:
            content_type = "application/octet-stream"

        # Read and serve the file
        body = file_path.read_bytes()

        return (
            Response(body=body, content_type=content_type)
            .with_header("Content-Length", str(len(body)))
            .with_header("Cache-Control", "public, max-age=3600")
        )
