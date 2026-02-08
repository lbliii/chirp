"""Static file serving middleware.

Serves files from a directory for matching URL prefixes.  Supports
root-level serving (``prefix="/"``) with automatic index file resolution
and optional custom error pages.

Falls through to the next handler for non-matching paths.
"""

import mimetypes
from pathlib import Path

from chirp.errors import HTTPError
from chirp.http.request import Request
from chirp.http.response import Response
from chirp.middleware.protocol import AnyResponse, Next


class StaticFiles:
    """Middleware that serves static files from a directory.

    Files are served for paths matching the configured prefix.
    Non-matching paths fall through to the next handler.

    Security: resolves symlinks and verifies the final path
    is within the configured directory to prevent path traversal.

    Usage::

        # Serve under a prefix
        app.add_middleware(StaticFiles(
            directory="./static",
            prefix="/static",
        ))

        # Root-level serving (static site)
        app.add_middleware(StaticFiles(
            directory="./public",
            prefix="/",
            not_found_page="404.html",
            cache_control="no-cache",
        ))
    """

    __slots__ = ("_cache_control", "_directory", "_index", "_not_found_page", "_prefix")

    def __init__(
        self,
        directory: str | Path,
        prefix: str = "/static",
        *,
        index: str = "index.html",
        not_found_page: str | None = None,
        cache_control: str = "public, max-age=3600",
    ) -> None:
        self._directory = Path(directory).resolve()
        self._index = index
        self._not_found_page = not_found_page
        self._cache_control = cache_control

        # Normalize prefix: ensure leading slash, strip trailing.
        # Root prefix "/" normalizes to "/" (not "").
        stripped = "/" + prefix.strip("/")
        self._prefix = stripped if stripped != "/" else ""

    async def __call__(self, request: Request, next: Next) -> AnyResponse:
        """Serve a static file or fall through."""
        # Only serve GET and HEAD
        if request.method not in ("GET", "HEAD"):
            return await next(request)

        path = request.path

        # Check if path matches prefix
        if self._prefix:
            if not path.startswith(self._prefix + "/") and path != self._prefix:
                return await next(request)
            # Extract relative file path after prefix
            relative = path[len(self._prefix) :].lstrip("/")
        else:
            # Root prefix — every path is a candidate
            relative = path.lstrip("/")

        # Resolve the file path and check for traversal
        file_path = (self._directory / relative).resolve() if relative else self._directory
        if not file_path.is_relative_to(self._directory):
            return Response(body="Forbidden", status=403)

        # Directory: try index file or redirect for trailing slash
        if file_path.is_dir():
            # If the request doesn't end with "/" and an index exists,
            # redirect to the trailing-slash URL.
            index_path = file_path / self._index
            if not path.endswith("/") and relative and index_path.is_file():
                return Response(
                    body="",
                    status=301,
                ).with_header("Location", path + "/")

            # Try to serve the index file
            if index_path.is_file():
                file_path = index_path
            else:
                return await self._handle_not_found(next, request)

        # Check if file exists and is a regular file
        if not file_path.is_file():
            return await self._handle_not_found(next, request)

        return self._serve_file(file_path)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _serve_file(self, file_path: Path, *, status: int = 200) -> Response:
        """Read a file and build a response."""
        content_type, _ = mimetypes.guess_type(str(file_path))
        if content_type is None:
            content_type = "application/octet-stream"

        body = file_path.read_bytes()

        return (
            Response(body=body, content_type=content_type, status=status)
            .with_header("Content-Length", str(len(body)))
            .with_header("Cache-Control", self._cache_control)
        )

    async def _handle_not_found(self, next: Next, request: Request) -> AnyResponse:
        """Fall through to the inner handler; serve custom 404 if it also fails.

        This lets application routes (e.g. SSE endpoints) take priority
        over the custom 404 page.  When ``not_found_page`` is set, the
        router's ``NotFound`` exception is caught and the custom page
        is served instead.
        """
        if not self._not_found_page:
            # No custom page — let the exception propagate normally
            return await next(request)

        error_path = (self._directory / self._not_found_page).resolve()
        if not (error_path.is_relative_to(self._directory) and error_path.is_file()):
            # Custom page doesn't exist — fall through
            return await next(request)

        try:
            return await next(request)
        except HTTPError as exc:
            if exc.status != 404:
                raise
            return self._serve_file(error_path, status=404)
