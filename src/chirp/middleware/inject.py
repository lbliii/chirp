"""HTML injection middleware.

Injects a snippet (e.g. a ``<script>`` tag) into every ``text/html``
response before a configurable target string (default: ``</body>``).

Useful for live-reload scripts, analytics, debug toolbars, or any
markup that should appear on every page without modifying templates.
"""

import logging
from dataclasses import replace

import anyio

from chirp.http.request import Request
from chirp.http.response import FileResponse, Response, StreamingResponse
from chirp.middleware.protocol import AnyResponse, Next
from chirp.middleware.streaming_html import async_stream_inject_before_body

_LOG = logging.getLogger("chirp.middleware.inject")


async def _materialize_html_file(response: FileResponse) -> Response | FileResponse:
    """Read a ``text/html`` FileResponse off disk into a buffered Response.

    Snippet injection needs the whole body, so a static HTML page served by
    :class:`~chirp.middleware.static.StaticFiles` is read into memory and
    returned as a :class:`~chirp.http.response.Response` that the existing
    body-injection path can rewrite. Status, headers, cookies, content type
    and render intent are preserved.

    Non-HTML FileResponses (CSS, images, large binaries) and unreadable files
    are returned unchanged so they keep streaming from disk.
    """
    if not response.resolved_content_type.startswith("text/html"):
        return response
    try:
        raw = await anyio.to_thread.run_sync(response.path.read_bytes)
    except OSError:
        _LOG.warning("HTMLInject: could not read %s for injection", response.path)
        return response
    return Response(
        body=raw.decode("utf-8", errors="replace"),
        status=response.status,
        content_type=response.resolved_content_type,
        headers=response.headers,
        cookies=response.cookies,
        render_intent=response.render_intent,
    )


class HTMLInject:
    """Middleware that injects HTML content into text/html responses.

    Affects ``Response`` objects whose ``content_type`` contains
    ``text/html`` and ``text/html`` :class:`~chirp.http.response.FileResponse`
    bodies (static HTML pages served by :class:`StaticFiles`), which are read
    from disk, injected, and returned as a buffered ``Response`` — snippet
    injection inherently needs the whole body, so streaming is moot here.
    ``StreamingResponse`` and ``SSEResponse`` are passed through unchanged
    (see :class:`AlpineInject` for streaming HTML).

    When *full_page_only* is ``True``, the snippet is injected **only**
    when the *before* target string is found in the response body.
    When ``False`` (the default), the snippet is appended at the end
    if the target string is absent.

    Usage::

        app.add_middleware(HTMLInject(
            '<script src="/__reload.js"></script>',
            before="</body>",
        ))
    """

    __slots__ = ("_full_page_only", "_skip_htmx", "_snippet", "_target")

    def __init__(
        self,
        snippet: str,
        *,
        before: str = "</body>",
        full_page_only: bool = False,
        skip_htmx: bool = False,
    ) -> None:
        self._snippet = snippet
        self._target = before
        self._full_page_only = full_page_only
        self._skip_htmx = skip_htmx

    async def __call__(self, request: Request, next: Next) -> AnyResponse:
        """Inject the snippet into HTML responses."""
        response = await next(request)

        # Static HTML files (FileResponse) are read into a buffered Response so
        # the snippet can be injected; non-HTML files stream through untouched.
        if isinstance(response, FileResponse):
            response = await _materialize_html_file(response)
        # Only modify concrete Response objects with HTML content
        if not isinstance(response, Response):
            return response
        if "text/html" not in response.content_type:
            return response
        if self._skip_htmx and request.is_htmx:
            return response
        # Prefer explicit render intent when available. Fall back to
        # request heuristics for unknown/legacy responses.
        if response.render_intent == "fragment":
            return response
        if response.render_intent == "unknown" and request.is_htmx:
            return response

        body = response.body
        if isinstance(body, bytes):
            body = body.decode("utf-8", errors="replace")

        if self._target in body:
            body = body.replace(self._target, self._snippet + self._target, 1)
        elif self._full_page_only:
            return response
        else:
            body = body + self._snippet

        return replace(response, body=body)


class StreamingHTMLInject(HTMLInject):
    """HTMLInject variant that also rewrites full-page StreamingResponse HTML."""

    __slots__ = ("_dedup_marker",)

    def __init__(
        self,
        snippet: str,
        *,
        before: str = "</body>",
        full_page_only: bool = False,
        dedup_marker: str | None = None,
        skip_htmx: bool = False,
    ) -> None:
        super().__init__(
            snippet,
            before=before,
            full_page_only=full_page_only,
            skip_htmx=skip_htmx,
        )
        self._dedup_marker = dedup_marker

    async def __call__(self, request: Request, next: Next) -> AnyResponse:
        response = await next(request)
        if isinstance(response, StreamingResponse):
            return self._streaming(response, request)
        if isinstance(response, FileResponse):
            response = await _materialize_html_file(response)
        if not isinstance(response, Response):
            return response
        if "text/html" not in response.content_type:
            return response
        if self._skip_htmx and request.is_htmx:
            return response
        if response.render_intent == "fragment":
            return response
        if response.render_intent == "unknown" and request.is_htmx:
            return response
        body = response.body
        if isinstance(body, bytes):
            body = body.decode("utf-8", errors="replace")
        if self._dedup_marker and self._dedup_marker in body:
            return response
        if self._target in body:
            body = body.replace(self._target, self._snippet + self._target, 1)
        elif self._full_page_only:
            return response
        else:
            body = body + self._snippet
        return replace(response, body=body)

    def _streaming(self, response: StreamingResponse, request: Request) -> StreamingResponse:
        if "text/html" not in response.content_type:
            return response
        if self._skip_htmx and request.is_htmx:
            return response
        if response.render_intent == "fragment":
            return response
        if response.render_intent == "unknown" and request.is_htmx:
            return response
        new_chunks = async_stream_inject_before_body(
            response.chunks,
            snippet=self._snippet,
            before=self._target,
            dedup_marker=self._dedup_marker,
            full_page_only=self._full_page_only,
        )
        return replace(response, chunks=new_chunks)


class AlpineInject(HTMLInject):
    """HTMLInject that skips when Alpine is already present in the page.

    Checks for ``data-chirp="alpine"`` in the response body before injecting.
    This prevents double-loading when the document already includes Alpine
    from another source.

    For :class:`~chirp.http.response.StreamingResponse` (e.g. ``Suspense``),
    the same snippet is inserted before the first ``</body>`` using a bounded
    buffer so ``</body>`` may be split across chunks.
    """

    __slots__ = ()

    async def __call__(self, request: Request, next: Next) -> AnyResponse:
        response = await next(request)
        if isinstance(response, StreamingResponse):
            return self._alpine_streaming(response, request)
        if isinstance(response, FileResponse):
            response = await _materialize_html_file(response)
        if not isinstance(response, Response):
            return response
        if "text/html" not in response.content_type:
            return response
        if response.render_intent == "fragment":
            return response
        if response.render_intent == "unknown" and request.is_htmx:
            return response
        body = response.body
        if isinstance(body, bytes):
            body = body.decode("utf-8", errors="replace")
        if 'data-chirp="alpine"' in body:
            return response
        # Reuse the fetched response — do not call ``next`` again via super().
        target = self._target
        snippet = self._snippet
        if target in body:
            body = body.replace(target, snippet + target, 1)
        elif self._full_page_only:
            return response
        else:
            body = body + snippet
        return replace(response, body=body)

    def _alpine_streaming(self, response: StreamingResponse, request: Request) -> StreamingResponse:
        if "text/html" not in response.content_type:
            return response
        if response.render_intent == "fragment":
            return response
        if response.render_intent == "unknown" and request.is_htmx:
            return response
        new_chunks = async_stream_inject_before_body(
            response.chunks,
            snippet=self._snippet,
            before=self._target,
            dedup_marker='data-chirp="alpine"',
            full_page_only=self._full_page_only,
        )
        return replace(response, chunks=new_chunks)


class ViewTransitionCssDebugWarning:
    """Log when the response body uses View Transition CSS but VT injection is off.

    Only runs in debug builds (see ``compiler._collect_builtin_middleware``).
    Helps catch ``view-transition-name`` / ``@view-transition`` in templates while
    ``AppConfig.view_transitions`` is ``False``, which disables HTMX global VT.
    """

    __slots__ = ()

    async def __call__(self, request: Request, next: Next) -> AnyResponse:
        response = await next(request)
        if not isinstance(response, Response):
            return response
        if "text/html" not in response.content_type:
            return response
        if response.render_intent == "fragment":
            return response
        if response.render_intent == "unknown" and request.is_htmx:
            return response

        body = response.body
        if isinstance(body, bytes):
            body = body.decode("utf-8", errors="replace")
        lowered = body.lower()
        if (
            "@view-transition" in lowered
            or "view-transition-name" in lowered
            or "::view-transition" in lowered
        ):
            _LOG.warning(
                "View Transition CSS detected in HTML but view_transitions is disabled — "
                "htmx navigations will not animate. Set AppConfig(view_transitions=True) "
                "for htmx swap transitions, or 'full' for cross-document transitions."
            )
        return response
